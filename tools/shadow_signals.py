"""
Shadow mode: candidate signals collected and logged on every run that NEVER change
a decision. They are evaluated later against realised returns
(evals/run/analyze_shadow.py) and only promoted into the engine through the normal
backtest / approval process (AGENTS.md, Rule 1).

Sources (all free tiers):
  - Engine candidate factors already computed by the engine even at weight 0
    (relative strength vs market / sector, overextension, VIX).
  - Finnhub /stock/recommendation  -> analyst consensus and its monthly change.
  - Finnhub /stock/earnings        -> EPS surprise history (last 4 quarters).
  - Alpha Vantage NEWS_SENTIMENT   -> relevance-weighted news sentiment
                                      (25 requests/day on the free key).
  - The production GPT news filter   -> signed score for the BUY candidates it
                                      evaluated (NEWS_SENT_ANALYSIS=true).

Enable with SHADOW_MODE_ENABLED=true. Rows are appended to the Google Sheet
SHADOW_LOG_FILE_ID (optional) and mirrored as shadow_* columns in the analysis sheet.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from tools import technical_engine
from tools.finnhub_client import auth_headers
from tools.general import ssl_verify

logger = logging.getLogger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
ALPHA_VANTAGE_DEFAULT_URL = "https://www.alphavantage.co/query"

# shadow column -> (engine layer, factor name)
ENGINE_CANDIDATES = {
    "rs_market": ("momentum", "rs_market"),
    "rs_sector": ("momentum", "rs_sector"),
    "overextension": ("risk", "overextension"),
    "vix": ("risk", "vix"),
}
CONTEXT_COLUMNS = ["date", "symbol", "price", "action", "technical_confidence", "regime", "filter_status"]


def is_enabled():
    return os.environ.get("SHADOW_MODE_ENABLED", "false").lower() == "true"


def _cfg():
    return technical_engine.load_config().get("shadow_mode", {})


def _finnhub(path, symbol):
    response = requests.get(f"{FINNHUB_BASE_URL}/{path}", params={"symbol": symbol},
                            headers=auth_headers(), timeout=10)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


def _consensus(period):
    counts = {k: period.get(k) or 0 for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
    total = sum(counts.values())
    if not total:
        return None, 0
    score = (2 * counts["strongBuy"] + counts["buy"] - counts["sell"] - 2 * counts["strongSell"]) / total
    return score, total


def analyst_recommendations(symbol):
    """Consensus in [-2, +2] (strong sell .. strong buy) and its change vs the prior month."""
    periods = sorted(_finnhub("stock/recommendation", symbol), key=lambda p: p.get("period", ""), reverse=True)
    if not periods:
        return {}
    score, count = _consensus(periods[0])
    prev, _ = _consensus(periods[1]) if len(periods) > 1 else (None, 0)
    return {
        "analyst_score": round(score, 4) if score is not None else None,
        "analyst_score_change": round(score - prev, 4) if score is not None and prev is not None else None,
        "analyst_count": count,
    }


def earnings_surprise(symbol):
    """Latest EPS surprise %, its 4-quarter average and number of beats."""
    quarters = sorted(_finnhub("stock/earnings", symbol), key=lambda q: q.get("period", ""), reverse=True)[:4]
    surprises = [q["surprisePercent"] for q in quarters if q.get("surprisePercent") is not None]
    if not surprises:
        return {}
    return {
        "eps_surprise_pct": round(float(surprises[0]), 4),
        "eps_surprise_avg4": round(sum(surprises) / len(surprises), 4),
        "eps_beats4": sum(1 for s in surprises if s > 0),
    }


class AlphaVantageBudget:
    """Caps NEWS_SENTIMENT calls per run and stops after a rate-limit answer."""

    def __init__(self, max_calls):
        self.remaining = max_calls
        self.exhausted = False

    def available(self):
        return self.remaining > 0 and not self.exhausted


def news_sentiment(symbol, days, budget):
    """Relevance-weighted Alpha Vantage ticker sentiment (-1 bearish .. +1 bullish)."""
    api_key = os.environ.get("ALPHA_API_KEY")
    if not api_key or not budget.available():
        return {}
    budget.remaining -= 1
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%dT%H%M")
    params = {"function": "NEWS_SENTIMENT", "tickers": symbol, "time_from": since, "limit": 50, "apikey": api_key}
    url = os.environ.get("ALPHA_VANTAGE_URL") or ALPHA_VANTAGE_DEFAULT_URL
    response = requests.get(url, params=params, timeout=20, verify=ssl_verify())
    response.raise_for_status()
    data = response.json()
    if "feed" not in data:
        if "Information" in data or "Note" in data:
            budget.exhausted = True
            logger.warning("⚠️ Alpha Vantage limit reached: news sentiment skipped for the rest of the run")
        return {}
    weighted, weights, articles = 0.0, 0.0, 0
    for item in data["feed"]:
        for ts in item.get("ticker_sentiment", []):
            if ts.get("ticker") == symbol:
                relevance = float(ts.get("relevance_score", 0) or 0)
                weighted += relevance * float(ts.get("ticker_sentiment_score", 0) or 0)
                weights += relevance
                articles += 1
    return {
        "news_sentiment_score": round(weighted / weights, 4) if weights > 0 else None,
        "news_articles": articles,
    }


def _safe(fn, *args):
    try:
        return fn(*args) or {}
    except Exception as e:
        logger.warning(f"⚠️ Shadow source {fn.__name__}({args[0]}) failed: {e}")
        return {}


def collect(analysis_df, analysis_results, run_time):
    """
    One shadow row per analysed symbol. Reads the final analysis_df (after every
    filter) and returns a new DataFrame — nothing passed in is modified.
    """
    cfg = _cfg()
    budget = AlphaVantageBudget(int(cfg.get("news_sentiment_max_calls", 20)))
    pause = float(cfg.get("request_pause_seconds", 1.0))
    metrics = {r["symbol"]: r["metrics"] for r in analysis_results}

    # BUY candidates first so the limited Alpha Vantage budget goes where it matters
    ordered = analysis_df.assign(_buy=analysis_df.get("action", pd.Series(dtype=object)).eq("BUY"))
    ordered = ordered.sort_values("_buy", ascending=False, kind="stable")

    rows = []
    for _, row in ordered.iterrows():
        symbol = row["symbol"]
        m = metrics.get(symbol, {})
        rec = {
            "date": run_time, "symbol": symbol, "price": row.get("current_price"),
            "action": row.get("action"), "technical_confidence": row.get("technical_confidence"),
            "regime": m.get("regime"), "filter_status": row.get("filter_status"),
        }
        factors = m.get("factors", {})
        for column, (layer, name) in ENGINE_CANDIDATES.items():
            rec[column] = factors.get(layer, {}).get(name)
        # The production GPT news filter (BUY candidates only) as a signed score, so the
        # filter itself can be judged: NEGATIVE 0.8 -> -0.8, POSITIVE 0.6 -> +0.6
        label, conf = row.get("news_sentiment_label"), row.get("news_sentiment_confidence")
        if isinstance(label, str) and conf is not None and not pd.isna(conf):
            rec["gpt_news_score"] = {"POSITIVE": 1, "NEGATIVE": -1}.get(label, 0) * float(conf)
        if cfg.get("analyst_recommendations", True):
            rec.update(_safe(analyst_recommendations, symbol))
        if cfg.get("earnings_surprise", True):
            rec.update(_safe(earnings_surprise, symbol))
        if cfg.get("news_sentiment", True):
            rec.update(_safe(news_sentiment, symbol, int(cfg.get("news_sentiment_days", 7)), budget))
        rows.append(rec)
        time.sleep(pause)  # Finnhub free tier: 60 requests/minute
    return pd.DataFrame(rows)


def add_shadow_columns(analysis_df, shadow_df):
    """Copy of analysis_df with every shadow signal as a shadow_<name> column."""
    out = analysis_df.copy()
    if shadow_df.empty:
        return out
    values = shadow_df.set_index("symbol")
    for column in [c for c in shadow_df.columns if c not in CONTEXT_COLUMNS]:
        out[f"shadow_{column}"] = out["symbol"].map(values[column])
    return out


def append_log(shadow_df, file_id, max_rows):
    """Append to the shadow log sheet. A failed read never overwrites the history."""
    from tools import google_handler
    if shadow_df.empty or not file_id:
        return
    existing = google_handler.load_data(file_id, allow_empty=True)
    if existing is None:
        logger.error("❌ Could not read the shadow log; not saving to avoid overwriting its history")
        return
    combined = pd.concat([f for f in (existing, shadow_df) if not f.empty], ignore_index=True).tail(max_rows)
    google_handler.save_dataframe_file_id(combined, file_id)
    logger.info(f"🕶️ Shadow log: +{len(shadow_df)} rows ({len(combined)} total)")
