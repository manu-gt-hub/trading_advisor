import json
import math
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from tools import technical_engine, custom_financial_calc as cfc, shadow_signals
from tools.risk_management import update_open_position
from tools.backtesting import run_backtest, _market_view


# ─── ENGINE_CONFIG_OVERRIDES ──────────────────────────────────────────

BASE = {"risk_management": {"stop_loss_atr_mult": 2.0, "exit_regimes": [], "max_holding_days": None},
        "relative_strength": {"sector_etfs": {"MSFT": "XLK"}}}


def test_overrides_apply_valid_paths():
    raw = json.dumps({"risk_management.stop_loss_atr_mult": 2.5,
                      "risk_management.exit_regimes": ["TRENDING_DOWN"],
                      "risk_management.max_holding_days": 30})
    cfg = technical_engine.apply_overrides(BASE, raw)
    assert cfg["risk_management"] == {"stop_loss_atr_mult": 2.5, "exit_regimes": ["TRENDING_DOWN"],
                                      "max_holding_days": 30}
    assert BASE["risk_management"]["stop_loss_atr_mult"] == 2.0  # original untouched


@pytest.mark.parametrize("raw", [
    '{"risk_management.stop_loss_atr_multiplier": 3}',   # typo -> unknown key
    '{"nope.stop": 1}',                                   # unknown path
    '{"risk_management.stop_loss_atr_mult": "3"}',       # type change
    'not json', '[1, 2]', '', None,
])
def test_overrides_reject_bad_input_without_crashing(raw):
    assert technical_engine.apply_overrides(BASE, raw) == BASE


def test_overrides_can_add_symbols_to_open_maps():
    cfg = technical_engine.apply_overrides(BASE, '{"relative_strength.sector_etfs.TSLA": "XLY"}')
    assert cfg["relative_strength"]["sector_etfs"] == {"MSFT": "XLK", "TSLA": "XLY"}


def test_overrides_read_from_env(monkeypatch):
    monkeypatch.setenv("ENGINE_CONFIG_OVERRIDES", '{"risk_management.stop_loss_atr_mult": 3.0}')
    try:
        assert technical_engine.load_config(force_reload=True)["risk_management"]["stop_loss_atr_mult"] == 3.0
    finally:
        monkeypatch.delenv("ENGINE_CONFIG_OVERRIDES")
        technical_engine.load_config(force_reload=True)


# ─── New engine factors ───────────────────────────────────────────────

FEATURES = {
    "price": 110.0, "sma50": 100.0, "sma200": 90.0, "ema20": 105.0, "ma50_slope": 1.0,
    "adx": 30.0, "plus_di": 30.0, "minus_di": 10.0, "rsi": 60.0, "macd": 1.0, "macd_signal": 0.5,
    "macd_hist_slope": 0.1, "macd_cross": 0, "stoch_rsi_k": 60.0, "roc": 0.03,
    "volatility": 0.015, "bb_upper": 120.0, "atr": 2.0,
}


def test_new_factors_at_weight_zero_do_not_change_the_decision():
    cfg = _with_weights(momentum__rs_market=0.0, momentum__rs_sector=0.0, risk__overextension=0.0, risk__vix=0.0)
    with_new = dict(FEATURES, rs_market_excess=0.2, rs_sector_excess=-0.1, vix=30.0)
    base = {k: v for k, v in FEATURES.items() if k != "atr"}
    a, b = technical_engine.decide(base, cfg), technical_engine.decide(with_new, cfg)
    assert (a["signal"], a["confidence"], a["sub_scores"]) == (b["signal"], b["confidence"], b["sub_scores"])
    # ...but they are computed, so shadow mode can log them
    assert {"rs_market", "rs_sector"} <= set(b["factors"]["momentum"])
    assert {"overextension", "vix"} <= set(b["factors"]["risk"])


def _with_weights(**weights):
    cfg = json.loads(json.dumps(technical_engine.load_config()))
    for path, w in weights.items():
        layer, name = path.split("__")
        cfg["layers"][layer]["indicators"][name]["weight"] = w
    return cfg


def test_relative_strength_raises_momentum_when_weighted():
    cfg = _with_weights(momentum__rs_market=0.3)
    strong = technical_engine.compute_momentum_score(dict(FEATURES, rs_market_excess=0.2), cfg)[0]
    weak = technical_engine.compute_momentum_score(dict(FEATURES, rs_market_excess=-0.2), cfg)[0]
    assert strong > weak


def test_overextension_and_vix_factor_values():
    risk = technical_engine.compute_risk_score(dict(FEATURES, price=113.0, vix=25.0))[1]
    assert risk["overextension"] == pytest.approx((4.0 - 1.5) / (4.0 - 1.5))  # (113-105)/2 = 4 ATR
    assert risk["vix"] == pytest.approx(0.5)
    calm = technical_engine.compute_risk_score(dict(FEATURES, price=106.0, vix=12.0))[1]
    assert calm["overextension"] == 0.0 and calm["vix"] == 0.0


# ─── Relative strength & market trend helpers ─────────────────────────

def test_excess_return_vs_benchmark():
    days = pd.date_range("2024-01-01", periods=5, freq="B")
    closes = pd.Series([100, 101, 102, 103, 110.0])
    bench = pd.Series([50, 50, 50, 50, 52.5], index=days)
    # symbol +10%, benchmark +5% -> 1.10 / 1.05 - 1
    assert cfc._excess_return(days, closes, bench, 4) == pytest.approx(1.10 / 1.05 - 1)
    assert cfc._excess_return(days, closes, None, 4) is None
    assert cfc._excess_return(days, closes, bench, 10) is None


def test_market_trend_from_closes_matches_rules():
    rising = pd.Series(np.linspace(100, 150, 60))
    assert cfc.market_trend_from_closes(rising) == ("BULLISH", 2.0)
    assert cfc.market_trend_from_closes(rising[::-1].reset_index(drop=True)) == ("BEARISH", -2.0)
    assert cfc.market_trend_from_closes(rising[:40]) == (None, 0.0)


def test_market_view_has_no_look_ahead():
    days = pd.date_range("2024-01-01", periods=80, freq="D")
    index = pd.Series(np.arange(80, dtype=float), index=days)
    vix = pd.Series(np.arange(80, dtype=float), index=days)
    sp500, ctx = _market_view({"index": index, "vix": vix, "market": index, "sector": None}, days[59])
    assert ctx["vix"] == 59.0
    assert ctx["benchmarks"]["market"].index.max() == days[59]
    assert sp500 == cfc.market_trend_from_closes(index.iloc[:60])


# ─── Regime exit ──────────────────────────────────────────────────────

def test_regime_exit_only_when_configured():
    with patch("tools.risk_management.get_rules", return_value={"exit_regimes": ["TRENDING_DOWN"]}):
        pos = update_open_position(100.0, 95.0, 101.0, 99.0, 110.0, regime="TRENDING_DOWN")
        assert pos["exit_reason"] == "regime_exit" and pos["exit_price"] == 99.0
        assert update_open_position(100.0, 95.0, 101.0, 99.0, 110.0, regime="RANGE")["exit_reason"] is None
        assert update_open_position(100.0, 95.0, 101.0, 99.0, 110.0, regime=None)["exit_reason"] is None
    assert update_open_position(100.0, 95.0, 101.0, 99.0, 110.0, regime="TRENDING_DOWN")["exit_reason"] is None


def test_backtest_regime_exit():
    closes = [100.0] * 5 + [101.0, 102.0, 101.5, 101.0]
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=len(closes), freq="B"),
                       "open": closes, "high": closes, "low": closes, "close": closes, "volume": 1000})

    def fake(symbol, d, price, **kwargs):
        regime = "TRENDING_DOWN" if len(d) == 8 else "TRENDING_UP"
        return {"evaluation": "BUY", "confidence": 0.7, "regime": regime, "signals": {"ATR_14": 2.0}}

    with patch("tools.backtesting.evaluate_buy_interest", side_effect=fake), \
         patch("tools.backtesting.get_rules", return_value={"exit_regimes": ["TRENDING_DOWN"]}), \
         patch("tools.risk_management.get_rules", return_value={"exit_regimes": ["TRENDING_DOWN"]}):
        res = run_backtest(df, "SYN", min_history=4, step_days=1)
    first = res["trades"][0]
    assert first["exit_reason"] == "regime_exit"
    assert first["actual_return_pct"] == pytest.approx(1.5)


# ─── Shadow mode ──────────────────────────────────────────────────────

def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def test_analyst_recommendations_consensus_and_change():
    payload = [
        {"period": "2026-10-01", "strongBuy": 10, "buy": 10, "hold": 0, "sell": 0, "strongSell": 0},
        {"period": "2026-11-01", "strongBuy": 5, "buy": 10, "hold": 5, "sell": 0, "strongSell": 0},
    ]
    with patch("tools.shadow_signals.requests.get", return_value=_resp(payload)):
        out = shadow_signals.analyst_recommendations("MSFT")
    assert out == {"analyst_score": 1.0, "analyst_score_change": -0.5, "analyst_count": 20}


def test_earnings_surprise():
    payload = [{"period": "2026-06-30", "surprisePercent": -2.0}, {"period": "2026-09-30", "surprisePercent": 4.0}]
    with patch("tools.shadow_signals.requests.get", return_value=_resp(payload)):
        out = shadow_signals.earnings_surprise("MSFT")
    assert out == {"eps_surprise_pct": 4.0, "eps_surprise_avg4": 1.0, "eps_beats4": 1}


def test_news_sentiment_weighting_and_budget(monkeypatch):
    monkeypatch.setenv("ALPHA_API_KEY", "k")
    feed = {"feed": [
        {"ticker_sentiment": [{"ticker": "MSFT", "relevance_score": "0.9", "ticker_sentiment_score": "0.4"}]},
        {"ticker_sentiment": [{"ticker": "MSFT", "relevance_score": "0.1", "ticker_sentiment_score": "-0.4"},
                              {"ticker": "AAPL", "relevance_score": "1", "ticker_sentiment_score": "-1"}]},
    ]}
    budget = shadow_signals.AlphaVantageBudget(1)
    with patch("tools.shadow_signals.requests.get", return_value=_resp(feed)) as get:
        out = shadow_signals.news_sentiment("MSFT", 7, budget)
        assert out == {"news_sentiment_score": pytest.approx(0.32), "news_articles": 2}
        assert shadow_signals.news_sentiment("MSFT", 7, budget) == {}  # budget spent
        assert get.call_count == 1


def test_news_sentiment_stops_after_rate_limit(monkeypatch):
    monkeypatch.setenv("ALPHA_API_KEY", "k")
    budget = shadow_signals.AlphaVantageBudget(5)
    with patch("tools.shadow_signals.requests.get", return_value=_resp({"Information": "rate limit"})):
        assert shadow_signals.news_sentiment("MSFT", 7, budget) == {}
    assert not budget.available()


def test_collect_never_mutates_inputs_and_survives_source_failures():
    analysis = pd.DataFrame({"symbol": ["A", "B"], "current_price": [10.0, 20.0], "action": ["HOLD", "BUY"],
                             "technical_confidence": [0.1, 0.7], "filter_status": ["", "✅ passed all filters"]})
    before = analysis.copy()
    results = [{"symbol": "A", "metrics": {"regime": "RANGE", "factors": {"momentum": {"rs_market": 0.2}}}},
               {"symbol": "B", "metrics": {"regime": "TRENDING_UP", "factors": {"risk": {"vix": 0.4}}}}]
    with patch("tools.shadow_signals.requests.get", side_effect=RuntimeError("down")), \
         patch("tools.shadow_signals.time.sleep"):
        shadow = shadow_signals.collect(analysis, results, "2026-11-09 18:00")
    pd.testing.assert_frame_equal(analysis, before)
    assert list(shadow["symbol"]) == ["B", "A"]  # BUY candidates first
    assert shadow.set_index("symbol").loc["A", "rs_market"] == 0.2
    enriched = shadow_signals.add_shadow_columns(analysis, shadow)
    assert {"shadow_rs_market", "shadow_vix"} <= set(enriched.columns)
    pd.testing.assert_frame_equal(analysis, before)


def test_append_log_never_overwrites_on_read_failure():
    shadow = pd.DataFrame({"date": ["d"], "symbol": ["A"]})
    with patch("tools.google_handler.load_data", return_value=None), \
         patch("tools.google_handler.save_dataframe_file_id") as save:
        shadow_signals.append_log(shadow, "file", 100)
    save.assert_not_called()
    existing = pd.DataFrame({"date": ["c"], "symbol": ["A"]})
    with patch("tools.google_handler.load_data", return_value=existing), \
         patch("tools.google_handler.save_dataframe_file_id") as save:
        shadow_signals.append_log(shadow, "file", 100)
    assert list(save.call_args[0][0]["date"]) == ["c", "d"]


# ─── main wiring ──────────────────────────────────────────────────────

def test_market_context_not_fetched_when_unused(monkeypatch):
    import main
    monkeypatch.delenv("SHADOW_MODE_ENABLED", raising=False)
    cfg = _with_weights(momentum__rs_market=0.0, momentum__rs_sector=0.0, risk__vix=0.0)
    with patch("main.technical_engine.load_config", return_value=cfg),          patch("main.historicals.get_close_series") as fetch:
        assert main.build_market_context(["MSFT"]) == {}
    fetch.assert_not_called()


def test_market_context_fetches_benchmark_when_rs_market_weighted(monkeypatch):
    import main
    monkeypatch.delenv("SHADOW_MODE_ENABLED", raising=False)
    cfg = _with_weights(momentum__rs_market=0.15, momentum__rs_sector=0.0, risk__vix=0.0)
    series = pd.Series([1.0, 2.0], index=pd.date_range("2024-01-01", periods=2))
    with patch("main.technical_engine.load_config", return_value=cfg),          patch("main.historicals.get_close_series", return_value=series) as fetch:
        ctx = main.build_market_context(["MSFT"])
    assert ctx["MSFT"]["benchmarks"]["market"] is series and ctx["MSFT"]["vix"] is None


def test_market_context_fetched_once_for_shadow(monkeypatch):
    import main
    monkeypatch.setenv("SHADOW_MODE_ENABLED", "true")
    series = pd.Series([1.0, 2.0], index=pd.date_range("2024-01-01", periods=2))
    with patch("main.historicals.get_close_series", return_value=series) as fetch:
        ctx = main.build_market_context(["MSFT", "AAPL", "ZZZZ"])
    assert fetch.call_count == 3  # VIX, SPY, XLK (shared by MSFT and AAPL)
    assert ctx["MSFT"]["vix"] == 2.0 and ctx["ZZZZ"]["benchmarks"]["sector"] is None


def test_blank_numeric_env_falls_back_to_default(monkeypatch):
    import main
    monkeypatch.setenv("MIN_RISK_REWARD_RATIO", "")
    assert main._env_number("MIN_RISK_REWARD_RATIO", 1.2) == 1.2
    monkeypatch.setenv("MIN_RISK_REWARD_RATIO", "1.5")
    assert main._env_number("MIN_RISK_REWARD_RATIO", 1.2) == 1.5


def test_missing_env_reports_names_only(monkeypatch):
    import main
    for n in main.REQUIRED_ENV + ["OPENAI_API_KEY", "GPT_MODEL_NAME", "SHADOW_LOG_FILE_ID", "ALPHA_API_KEY"]:
        monkeypatch.setenv(n, "x")
    monkeypatch.setenv("SHADOW_MODE_ENABLED", "true")
    monkeypatch.setenv("LLM_AUDIT_ENABLED", "false")
    monkeypatch.setenv("NEWS_SENT_ANALYSIS", "")
    assert main.missing_env() == []
    monkeypatch.setenv("SHADOW_LOG_FILE_ID", "")
    monkeypatch.setenv("GDRIVE_FILE_ID", " ")
    monkeypatch.delenv("OPENAI_API_KEY")
    assert main.missing_env() == ["GDRIVE_FILE_ID", "SHADOW_LOG_FILE_ID"]  # OpenAI not needed: LLM off
    monkeypatch.setenv("NEWS_SENT_ANALYSIS", "true")
    assert "OPENAI_API_KEY" in main.missing_env()
