"""
analyze_shadow.py — does a shadow signal predict returns?

Reads the shadow log (SHADOW_LOG_FILE_ID sheet or a CSV export), fetches prices
from Yahoo Finance (free) and measures, for every shadow signal, how it relates to
the return over the next 5 / 10 / 20 trading days:

  - Spearman rank correlation (IC), pooled and averaged per symbol
  - average forward return by quintile, and top-minus-bottom spread

A signal is a promotion candidate only with enough data (default: >= 60 distinct
days and >= 300 observations) and a consistent sign across horizons. Promotion
itself is an engine change: backtest / approval per AGENTS.md, Rule 1.

Usage:
  python evals/run/analyze_shadow.py --csv shadow_log.csv
  python evals/run/analyze_shadow.py --from-drive            # uses SHADOW_LOG_FILE_ID
  python evals/run/analyze_shadow.py --csv log.csv --windows-certs
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from download_historicals import download, make_session, windows_ca_bundle  # noqa: E402
from tools.shadow_signals import CONTEXT_COLUMNS  # noqa: E402

HORIZONS = (5, 10, 20)


def load_log(args):
    if args.csv:
        return pd.read_csv(args.csv)
    from dotenv import load_dotenv
    from tools import google_handler
    load_dotenv()
    df = google_handler.load_data(os.environ.get("SHADOW_LOG_FILE_ID"), allow_empty=True)
    if df is None:
        sys.exit("Could not read the shadow log sheet (SHADOW_LOG_FILE_ID / GDRIVE_CREDENTIALS_JSON).")
    return df


def forward_returns(log, session, period):
    """Adds fwd5/fwd10/fwd20: close h trading days after the run date vs the logged price."""
    out = []
    for symbol, rows in log.groupby("symbol"):
        prices = download(symbol, period, session)
        if prices is None or prices.empty:
            print(f"  ⚠️ no prices for {symbol}")
            continue
        closes = prices.set_index(pd.to_datetime(prices["date"]))["close"]
        rows = rows.copy()
        for h in HORIZONS:
            vals = []
            for day, price in zip(rows["day"], rows["price"]):
                pos = closes.index.searchsorted(day, side="right")  # first close after the run day
                target = pos - 1 + h
                vals.append(closes.iloc[target] / price - 1 if target < len(closes) and price > 0 else np.nan)
            rows[f"fwd{h}"] = vals
        out.append(rows)
    return pd.concat(out, ignore_index=True) if out else log.iloc[0:0]


def evaluate(df, feature, min_days, min_obs):
    data = df[[feature, "symbol", "day"] + [f"fwd{h}" for h in HORIZONS]].dropna(subset=[feature])
    n, days = len(data), data["day"].nunique()
    result = {"feature": feature, "obs": n, "days": days}
    for h in HORIZONS:
        d = data.dropna(subset=[f"fwd{h}"])
        if len(d) < 20 or d[feature].nunique() < 3:
            result[f"ic{h}"] = np.nan
            continue
        result[f"ic{h}"] = d[feature].rank().corr(d[f"fwd{h}"].rank())
    d = data.dropna(subset=["fwd20"])
    if len(d) >= 50 and d[feature].nunique() >= 5:
        q = pd.qcut(d[feature].rank(method="first"), 5, labels=False)
        means = d.groupby(q)["fwd20"].mean() * 100
        result["q1_fwd20"], result["q5_fwd20"] = means.iloc[0], means.iloc[-1]
        result["spread_pp"] = means.iloc[-1] - means.iloc[0]
    ics = [result.get(f"ic{h}") for h in HORIZONS]
    consistent = all(pd.notna(x) for x in ics) and (all(x > 0 for x in ics) or all(x < 0 for x in ics))
    if n < min_obs or days < min_days:
        result["verdict"] = "insufficient data"
    elif consistent and abs(result["ic20"]) >= 0.05:
        result["verdict"] = "CANDIDATE (backtest before promoting)"
    else:
        result["verdict"] = "no reliable edge"
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", help="shadow log exported as CSV")
    ap.add_argument("--from-drive", action="store_true", help="read SHADOW_LOG_FILE_ID from Google Drive")
    ap.add_argument("--min-days", type=int, default=60)
    ap.add_argument("--min-obs", type=int, default=300)
    ap.add_argument("--period", default="2y", help="price history to download")
    ap.add_argument("--ca-bundle", default=os.environ.get("YF_CA_BUNDLE"))
    ap.add_argument("--windows-certs", action="store_true")
    args = ap.parse_args()
    if not args.csv and not args.from_drive:
        ap.error("use --csv FILE or --from-drive")

    log = load_log(args)
    if log.empty:
        sys.exit("Shadow log is empty.")
    log["day"] = pd.to_datetime(log["date"]).dt.normalize()
    log["price"] = pd.to_numeric(log["price"], errors="coerce")
    features = [c for c in log.columns if c not in CONTEXT_COLUMNS + ["day"]
                and pd.to_numeric(log[c], errors="coerce").notna().any()]
    for c in features:
        log[c] = pd.to_numeric(log[c], errors="coerce")

    session = make_session(windows_ca_bundle() if args.windows_certs else args.ca_bundle)
    df = forward_returns(log, session, args.period)
    print(f"Shadow log: {len(log)} rows, {log['day'].nunique()} days, {log['symbol'].nunique()} symbols "
          f"({log['day'].min().date()} → {log['day'].max().date()})\n")

    report = pd.DataFrame([evaluate(df, f, args.min_days, args.min_obs) for f in features])
    pd.set_option("display.width", 200)
    print(report.round(3).to_string(index=False))
    print("\nIC = Spearman rank correlation with the forward return (|IC| ≥ 0.05 is meaningful for daily signals).")
    print("spread_pp = avg 20-day return of the top quintile minus the bottom quintile, in percentage points.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
