import pandas as pd
import numpy as np
import logging
from tools.custom_financial_calc import evaluate_buy_interest

logger = logging.getLogger(__name__)


def run_backtest(df, symbol, target_profit_pct=10.0, max_holding_days=30,
                 min_history=250, step_days=5, sp500_mock=("NEUTRAL", 0.0)):
    """
    Backtest the technical analysis signals over historical data.

    For each evaluation day (starting after min_history rows), runs evaluate_buy_interest
    using only data available up to that day. If the signal is BUY, checks whether the
    stock hits the target_profit_pct within max_holding_days trading days.

    Parameters:
        df (pd.DataFrame): Full historical data with columns: date, open, high, low, close, volume.
        symbol (str): Stock ticker symbol.
        target_profit_pct (float): Profit target in % (e.g., 10.0 means +10%).
        max_holding_days (int): Max trading days to hold a BUY position.
        min_history (int): Minimum rows of history before starting to evaluate.
        step_days (int): Evaluate every N days to speed up backtesting.
        sp500_mock (tuple): Mock S&P500 trend to avoid external calls (trend, score).

    Returns:
        dict with backtest results including trades, win rate, avg return, etc.
    """
    df = df.copy()
    df.columns = df.columns.str.lower()
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.sort_values("date").reset_index(drop=True)

    trades = []
    total_signals = {"BUY": 0, "SELL": 0, "HOLD": 0, "EVALUATION_FAILED": 0}

    for i in range(min_history, len(df) - max_holding_days, step_days):
        # Use only data up to day i (look-ahead bias prevention)
        hist_slice = df.iloc[:i + 1].copy()
        entry_price = float(df.iloc[i]["close"])
        entry_date = df.iloc[i]["date"]

        try:
            result = evaluate_buy_interest(symbol, hist_slice, entry_price)
        except Exception as e:
            logger.warning(f"Backtest eval failed at index {i}: {e}")
            continue

        decision = result["evaluation"]
        confidence = result["confidence"]
        total_signals[decision] = total_signals.get(decision, 0) + 1

        if decision != "BUY":
            continue

        # Track the BUY trade outcome
        future = df.iloc[i + 1: i + 1 + max_holding_days]
        if future.empty:
            continue

        # Check if target was hit during holding period
        max_price = float(future["close"].max())
        max_return_pct = ((max_price - entry_price) / entry_price) * 100
        hit_target = max_return_pct >= target_profit_pct

        # Calculate actual return at end of holding period
        exit_price = float(future.iloc[-1]["close"])
        actual_return_pct = ((exit_price - entry_price) / entry_price) * 100

        # Find the day the target was hit (if it was)
        days_to_target = None
        if hit_target:
            for j, (_, row) in enumerate(future.iterrows(), 1):
                pct = ((float(row["close"]) - entry_price) / entry_price) * 100
                if pct >= target_profit_pct:
                    days_to_target = j
                    break

        trades.append({
            "entry_date": entry_date,
            "entry_price": round(entry_price, 2),
            "confidence": round(confidence, 2),
            "max_return_pct": round(max_return_pct, 2),
            "actual_return_pct": round(actual_return_pct, 2),
            "hit_target": hit_target,
            "days_to_target": days_to_target,
        })

    # Compute summary statistics
    if not trades:
        return {
            "symbol": symbol,
            "total_signals": total_signals,
            "total_buy_signals": 0,
            "trades": [],
            "summary": "No BUY signals generated during backtest period.",
        }

    trades_df = pd.DataFrame(trades)
    wins = trades_df["hit_target"].sum()
    total = len(trades_df)
    win_rate = wins / total if total > 0 else 0.0

    return {
        "symbol": symbol,
        "target_profit_pct": target_profit_pct,
        "max_holding_days": max_holding_days,
        "total_signals": total_signals,
        "total_buy_signals": total,
        "wins": int(wins),
        "losses": total - int(wins),
        "win_rate": round(win_rate, 4),
        "avg_max_return_pct": round(trades_df["max_return_pct"].mean(), 2),
        "avg_actual_return_pct": round(trades_df["actual_return_pct"].mean(), 2),
        "median_actual_return_pct": round(trades_df["actual_return_pct"].median(), 2),
        "worst_trade_pct": round(trades_df["actual_return_pct"].min(), 2),
        "best_trade_pct": round(trades_df["actual_return_pct"].max(), 2),
        "avg_days_to_target": round(trades_df["days_to_target"].dropna().mean(), 1) if wins > 0 else None,
        "trades": trades,
    }


def format_backtest_report(results):
    """Format backtest results into a readable string report."""
    if results["total_buy_signals"] == 0:
        return f"Backtest {results['symbol']}: No BUY signals generated."

    lines = [
        f"═══════════════════════════════════════════",
        f"  BACKTEST REPORT: {results['symbol']}",
        f"═══════════════════════════════════════════",
        f"  Target profit:     {results['target_profit_pct']}%",
        f"  Max holding:       {results['max_holding_days']} trading days",
        f"───────────────────────────────────────────",
        f"  Signal distribution: {results['total_signals']}",
        f"  BUY signals:       {results['total_buy_signals']}",
        f"  Wins (hit target): {results['wins']}",
        f"  Losses:            {results['losses']}",
        f"  WIN RATE:          {results['win_rate']:.1%}",
        f"───────────────────────────────────────────",
        f"  Avg max return:    {results['avg_max_return_pct']:+.2f}%",
        f"  Avg actual return: {results['avg_actual_return_pct']:+.2f}%",
        f"  Median return:     {results['median_actual_return_pct']:+.2f}%",
        f"  Best trade:        {results['best_trade_pct']:+.2f}%",
        f"  Worst trade:       {results['worst_trade_pct']:+.2f}%",
    ]
    if results["avg_days_to_target"]:
        lines.append(f"  Avg days to target:{results['avg_days_to_target']:.0f} days")
    lines.append(f"═══════════════════════════════════════════")
    return "\n".join(lines)
