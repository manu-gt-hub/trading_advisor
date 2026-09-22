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
    "amzn_hist_data.csv": "AMZN",
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
            step_days=5,
        )

        all_results.append(results)
        print(format_backtest_report(results))

    # Print summary table
    if all_results:
        print("\n")
        print("=" * 100)
        print("  CONSOLIDATED BACKTEST SUMMARY")
        print("=" * 100)
        print(f"  {'Symbol':<8} {'BUYs':>5} {'Wins':>5} {'Win%':>7} {'AvgRet':>8} {'Expect':>8} {'PF':>6} {'AvgMFE':>8} {'AvgMAE':>8} {'System%':>9} {'B&H%':>9}")
        print("-" * 100)

        total_buys = 0
        total_wins = 0
        all_returns = []
        all_trades = []

        for r in all_results:
            sym = r["symbol"]
            buys = r["total_buy_signals"]
            bh = r.get("benchmark_buy_hold_pct", 0)
            if buys > 0:
                wins = r["wins"]
                wr = r["win_rate"]
                avg = r["avg_actual_return_pct"]
                exp = r.get("expectancy_pct", 0)
                pf = r.get("profit_factor", 0)
                mfe = r.get("avg_mfe_pct", 0)
                mae = r.get("avg_mae_pct", 0)
                sys_ret = r.get("system_cumulative_return_pct", 0)
                pf_str = f"{pf:.2f}" if pf != float("inf") else "inf"
                print(f"  {sym:<8} {buys:>5} {wins:>5} {wr:>6.1%} {avg:>+7.2f}% {exp:>+7.2f}% {pf_str:>6} {mfe:>+7.2f}% {mae:>+7.2f}% {sys_ret:>+8.2f}% {bh:>+8.2f}%")
                total_buys += buys
                total_wins += wins
                all_returns.extend([t["actual_return_pct"] for t in r["trades"]])
                all_trades.extend(r["trades"])
            else:
                print(f"  {sym:<8} {buys:>5}     -       -        -        -      -        -        -         -  {bh:>+8.2f}%")

        print("-" * 100)
        if total_buys > 0:
            overall_wr = total_wins / total_buys
            avg_all = sum(all_returns) / len(all_returns)
            all_df = pd.DataFrame(all_trades)
            w = all_df[all_df["actual_return_pct"] > 0]
            l = all_df[all_df["actual_return_pct"] <= 0]
            avg_w = float(w["actual_return_pct"].mean()) if len(w) > 0 else 0
            avg_l = float(l["actual_return_pct"].mean()) if len(l) > 0 else 0
            gp = float(w["actual_return_pct"].sum()) if len(w) > 0 else 0
            gl = abs(float(l["actual_return_pct"].sum())) if len(l) > 0 else 0
            pf_t = gp / gl if gl > 0 else float("inf")
            exp_t = overall_wr * avg_w + (1 - overall_wr) * avg_l
            mfe_t = float(all_df["mfe_pct"].mean())
            mae_t = float(all_df["mae_pct"].mean())
            pf_str = f"{pf_t:.2f}" if pf_t != float("inf") else "inf"
            print(f"  {'TOTAL':<8} {total_buys:>5} {total_wins:>5} {overall_wr:>6.1%} {avg_all:>+7.2f}% {exp_t:>+7.2f}% {pf_str:>6} {mfe_t:>+7.2f}% {mae_t:>+7.2f}%")
        print("=" * 100)

        # MAE/MFE analysis by MFE band
        if all_trades:
            all_df = pd.DataFrame(all_trades)
            print("\n")
            print("=" * 80)
            print("  MAE / MFE ANALYSIS")
            print("=" * 80)

            # MFE distribution: how far did trades go in our favor?
            mfe_bands = [(0, 2), (2, 4), (4, 6), (6, 10), (10, 100)]
            print(f"\n  MFE bands (max favorable excursion):")
            print(f"  {'MFE range':>12} {'Trades':>7} {'AvgRet':>8} {'AvgMAE':>8} {'Win%':>7} {'Trailing%':>10}")
            print(f"  {'-'*60}")
            for lo, hi in mfe_bands:
                band = all_df[(all_df["mfe_pct"] >= lo) & (all_df["mfe_pct"] < hi)]
                if len(band) == 0:
                    continue
                label = f"{lo}-{hi}%" if hi < 100 else f"{lo}%+"
                avg_ret = band["actual_return_pct"].mean()
                avg_mae = band["mae_pct"].mean()
                wr = band["hit_target"].mean()
                trailing_n = len(band[band["exit_reason"] == "trailing_stop"])
                trailing_pct = trailing_n / len(band) * 100
                print(f"  {label:>12} {len(band):>7} {avg_ret:>+7.2f}% {avg_mae:>+7.2f}% {wr:>6.1%} {trailing_pct:>9.1f}%")

            # MAE distribution: how far did trades go against us?
            mae_bands = [(-100, -6), (-6, -4), (-4, -2), (-2, 0), (0, 100)]
            print(f"\n  MAE bands (max adverse excursion):")
            print(f"  {'MAE range':>12} {'Trades':>7} {'AvgRet':>8} {'AvgMFE':>8} {'Win%':>7}")
            print(f"  {'-'*50}")
            for lo, hi in mae_bands:
                band = all_df[(all_df["mae_pct"] >= lo) & (all_df["mae_pct"] < hi)]
                if len(band) == 0:
                    continue
                label = f"{lo}%" if lo == -100 else f"{lo}-{hi}%" if hi < 100 else f"{lo}%+"
                if lo == -100:
                    label = f"<{hi}%"
                avg_ret = band["actual_return_pct"].mean()
                avg_mfe = band["mfe_pct"].mean()
                wr = band["hit_target"].mean()
                print(f"  {label:>12} {len(band):>7} {avg_ret:>+7.2f}% {avg_mfe:>+7.2f}% {wr:>6.1%}")

            # Timing: when does MFE/MAE happen?
            print(f"\n  Timing (average day of MFE/MAE by exit reason):")
            print(f"  {'Exit reason':>15} {'Trades':>7} {'DayMFE':>8} {'DayMAE':>8} {'AvgMFE':>8} {'AvgMAE':>8} {'AvgRet':>8}")
            print(f"  {'-'*65}")
            for reason in ["target", "trailing_stop", "max_hold"]:
                subset = all_df[all_df["exit_reason"] == reason]
                if len(subset) == 0:
                    continue
                print(f"  {reason:>15} {len(subset):>7} {subset['day_of_mfe'].mean():>7.1f} {subset['day_of_mae'].mean():>7.1f} {subset['mfe_pct'].mean():>+7.2f}% {subset['mae_pct'].mean():>+7.2f}% {subset['actual_return_pct'].mean():>+7.2f}%")

            # Trailing stop detail: what gain% did they have when stopped?
            trailing_trades = all_df[all_df["exit_reason"] == "trailing_stop"]
            if len(trailing_trades) > 0:
                print(f"\n  Trailing stop detail:")
                print(f"    Trades stopped: {len(trailing_trades)}")
                gains_at_trigger = trailing_trades["gain_at_trailing_trigger"].dropna()
                if len(gains_at_trigger) > 0:
                    print(f"    Avg gain at trigger:   {gains_at_trigger.mean():+.2f}%")
                    print(f"    Median gain at trigger:{gains_at_trigger.median():+.2f}%")
                print(f"    Avg MFE before exit:   {trailing_trades['mfe_pct'].mean():+.2f}%")
                print(f"    Avg final return:      {trailing_trades['actual_return_pct'].mean():+.2f}%")
                print(f"    Leakage (MFE - exit):  {(trailing_trades['mfe_pct'] - trailing_trades['actual_return_pct']).mean():+.2f}pp")

            print("=" * 80)


if __name__ == "__main__":
    run_all_backtests()
