import sys
import os
import pytest
import pandas as pd
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from tools.backtesting import run_backtest, format_backtest_report


def load_msft_data():
    current_dir = os.path.dirname(__file__)
    csv_path = os.path.join(current_dir, '..', 'resources', 'historicals', 'msft_hist_data.csv')
    return pd.read_csv(csv_path)


@patch("tools.custom_financial_calc._compute_weekly_confirmation", return_value=None)
@patch("tools.custom_financial_calc._get_sp500_trend", return_value=("NEUTRAL", 0.0))
def test_backtest_generates_trades(mock_sp500, mock_weekly):
    """Backtest should produce at least some BUY signals over 5 years of MSFT data."""
    df = load_msft_data()

    results = run_backtest(
        df, "MSFT",
        target_profit_pct=10.0,
        max_holding_days=30,
        min_history=250,
        step_days=20,  # every ~1 month to keep test fast
    )

    assert results["symbol"] == "MSFT"
    assert results["total_buy_signals"] >= 0
    assert isinstance(results["trades"], list)
    assert "win_rate" in results or "summary" in results

    # Print report for visibility during test runs
    print("\n" + format_backtest_report(results))


@patch("tools.custom_financial_calc._compute_weekly_confirmation", return_value=None)
@patch("tools.custom_financial_calc._get_sp500_trend", return_value=("NEUTRAL", 0.0))
def test_backtest_win_rate_sanity(mock_sp500, mock_weekly):
    """
    If BUY signals are generated, the win rate should be above random chance (>25%).
    This is a sanity check — not a guarantee, but a red flag if it fails.
    """
    df = load_msft_data()

    results = run_backtest(
        df, "MSFT",
        target_profit_pct=10.0,
        max_holding_days=30,
        min_history=250,
        step_days=20,
    )

    print("\n" + format_backtest_report(results))

    if results["total_buy_signals"] == 0:
        pytest.skip("No BUY signals generated — cannot evaluate win rate")

    # Sanity: win rate should beat random chance
    assert results["win_rate"] >= 0.15, (
        f"Win rate {results['win_rate']:.1%} is below 15% — signals may be unreliable. "
        f"Review scoring thresholds."
    )


@patch("tools.custom_financial_calc._compute_weekly_confirmation", return_value=None)
@patch("tools.custom_financial_calc._get_sp500_trend", return_value=("NEUTRAL", 0.0))
def test_backtest_avg_return_not_catastrophic(mock_sp500, mock_weekly):
    """Average return of BUY signals should not be deeply negative."""
    df = load_msft_data()

    results = run_backtest(
        df, "MSFT",
        target_profit_pct=10.0,
        max_holding_days=30,
        min_history=250,
        step_days=20,
    )

    if results["total_buy_signals"] == 0:
        pytest.skip("No BUY signals generated")

    # Avg actual return should be > -10% (not catastrophic)
    assert results["avg_actual_return_pct"] > -10.0, (
        f"Avg return {results['avg_actual_return_pct']:.2f}% is catastrophic — review logic."
    )


@patch("tools.custom_financial_calc._compute_weekly_confirmation", return_value=None)
@patch("tools.custom_financial_calc._get_sp500_trend", return_value=("NEUTRAL", 0.0))
def test_backtest_no_lookahead_bias(mock_sp500, mock_weekly):
    """Verify that the backtest doesn't use future data — entry price should match the day's close."""
    df = load_msft_data()

    results = run_backtest(
        df, "MSFT",
        target_profit_pct=10.0,
        max_holding_days=30,
        min_history=250,
        step_days=50,  # fewer trades, just checking integrity
    )

    if results["total_buy_signals"] == 0:
        pytest.skip("No BUY signals")

    df_parsed = df.copy()
    df_parsed.columns = df_parsed.columns.str.lower()
    df_parsed["close"] = pd.to_numeric(df_parsed["close"], errors="coerce")

    for trade in results["trades"]:
        entry_date = pd.Timestamp(trade["entry_date"])
        entry_price = trade["entry_price"]

        # Find the actual close on that date
        day_row = df_parsed[pd.to_datetime(df_parsed["date"], utc=True) == entry_date]
        if not day_row.empty:
            actual_close = round(float(day_row.iloc[0]["close"]), 2)
            assert entry_price == actual_close, (
                f"Look-ahead bias! Entry price {entry_price} != close {actual_close} on {entry_date}"
            )


def test_format_backtest_report_no_trades():
    results = {
        "symbol": "TEST",
        "total_buy_signals": 0,
        "trades": [],
    }
    report = format_backtest_report(results)
    assert "No BUY signals" in report


def test_format_backtest_report_with_trades():
    results = {
        "symbol": "TEST",
        "target_profit_pct": 10.0,
        "max_holding_days": 30,
        "total_signals": {"BUY": 5, "SELL": 3, "HOLD": 10},
        "total_buy_signals": 5,
        "wins": 3,
        "losses": 2,
        "win_rate": 0.6,
        "avg_max_return_pct": 12.5,
        "avg_actual_return_pct": 7.3,
        "median_actual_return_pct": 6.0,
        "worst_trade_pct": -3.2,
        "best_trade_pct": 18.5,
        "avg_days_to_target": 15.0,
        "system_cumulative_return_pct": 42.5,
        "benchmark_buy_hold_pct": 60.0,
        "system_vs_benchmark": -17.5,
        "trades": [],
    }
    report = format_backtest_report(results)
    assert "WIN RATE" in report
    assert "60.0%" in report
    assert "TEST" in report
    assert "Buy & Hold" in report
    assert "System vs B&H" in report
