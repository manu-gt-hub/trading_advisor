"""
Run backtesting across all historical data CSVs in resources/historicals/.
Handles both Yahoo Finance and NASDAQ CSV formats.
"""
import os
import sys
import pandas as pd
import logging
from unittest.mock import patch

from tools.backtesting import run_backtest, format_backtest_report

logging.basicConfig(level=logging.WARNING)

HIST_DIR = os.path.join(os.path.dirname(__file__), "resources", "historicals")

# Map CSV filenames to stock symbols
FILE_SYMBOL_MAP = {
    "msft_hist_data.csv": "MSFT",
    "apple_hist_data.csv": "AAPL",
    "nvidia_hist_data.csv": "NVDA",
    "ko_hist_data.csv": "KO",
    "meta_hist_data.csv": "META",
    "visa_hist_data.csv": "V",
}


def load_and_normalize_csv(filepath):
    """Load a CSV and normalize to standard columns: date, open, high, low, close, volume."""
    df = pd.read_csv(filepath)

    # Detect NASDAQ format (has 'Close/Last' column and $ signs)
    if "Close/Last" in df.columns:
        # NASDAQ format: Date, Close/Last, Volume, Open, High, Low
        # Values have $ prefix
        for col in ["Close/Last", "Open", "High", "Low"]:
            df[col] = df[col].astype(str).str.replace("$", "", regex=False).astype(float)

        df = df.rename(columns={
            "Date": "date",
            "Close/Last": "close",
            "Volume": "volume",
            "Open": "open",
            "High": "high",
            "Low": "low",
        })
        # Parse NASDAQ date format (MM/DD/YYYY)
        df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y")
    else:
        # Yahoo Finance format: date, open, high, low, close, volume, ...
        df.columns = df.columns.str.lower()
        df["date"] = pd.to_datetime(df["date"])

    # Keep only needed columns
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df = df.sort_values("date").reset_index(drop=True)

    return df


@patch("tools.custom_financial_calc._compute_weekly_confirmation", return_value=None)
@patch("tools.custom_financial_calc._get_sp500_trend", return_value=("NEUTRAL", 0.0))
def run_all_backtests(mock_sp500, mock_weekly):
    """Run backtests on all CSV files and print a summary."""
    all_results = []

    for filename, symbol in FILE_SYMBOL_MAP.items():
        filepath = os.path.join(HIST_DIR, filename)
        if not os.path.exists(filepath):
            print(f"⚠️  Skipping {symbol}: {filename} not found")
            continue

        print(f"\n🔄 Running backtest for {symbol}...")
        df = load_and_normalize_csv(filepath)
        print(f"   Loaded {len(df)} rows ({df['date'].min().date()} to {df['date'].max().date()})")

        results = run_backtest(
            df, symbol,
            target_profit_pct=10.0,
            max_holding_days=30,
            min_history=250,
            step_days=10,
        )

        all_results.append(results)
        print(format_backtest_report(results))

    # Print summary table
    if all_results:
        print("\n")
        print("═" * 70)
        print("  CONSOLIDATED BACKTEST SUMMARY")
        print("═" * 70)
        print(f"  {'Symbol':<8} {'BUYs':>6} {'Wins':>6} {'Win%':>8} {'AvgRet%':>9} {'MedRet%':>9} {'Worst%':>9} {'Best%':>9}")
        print("─" * 70)

        total_buys = 0
        total_wins = 0
        all_returns = []

        for r in all_results:
            sym = r["symbol"]
            buys = r["total_buy_signals"]
            if buys > 0:
                wins = r["wins"]
                wr = r["win_rate"]
                avg = r["avg_actual_return_pct"]
                med = r["median_actual_return_pct"]
                worst = r["worst_trade_pct"]
                best = r["best_trade_pct"]
                print(f"  {sym:<8} {buys:>6} {wins:>6} {wr:>7.1%} {avg:>+8.2f}% {med:>+8.2f}% {worst:>+8.2f}% {best:>+8.2f}%")
                total_buys += buys
                total_wins += wins
                all_returns.extend([t["actual_return_pct"] for t in r["trades"]])
            else:
                print(f"  {sym:<8} {buys:>6}      -        -         -         -         -         -")

        print("─" * 70)
        if total_buys > 0:
            overall_wr = total_wins / total_buys
            avg_all = sum(all_returns) / len(all_returns)
            sorted_returns = sorted(all_returns)
            med_all = sorted_returns[len(sorted_returns) // 2]
            print(f"  {'TOTAL':<8} {total_buys:>6} {total_wins:>6} {overall_wr:>7.1%} {avg_all:>+8.2f}% {med_all:>+8.2f}% {min(all_returns):>+8.2f}% {max(all_returns):>+8.2f}%")
        print("═" * 70)


if __name__ == "__main__":
    run_all_backtests()
