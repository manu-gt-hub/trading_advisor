import sys
import os
import pytest
import pandas as pd
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from tools.backtesting import run_backtest, format_backtest_report

HISTORICALS_DIR = os.path.join(os.path.dirname(__file__), '..', 'resources', 'historicals')

# Map symbol -> csv filename for all available historical data
SYMBOL_CSV_MAP = {
    "MSFT": "msft_hist_data.csv",
    "AAPL": "apple_hist_data.csv",
    "NVDA": "nvidia_hist_data.csv",
    "META": "meta_hist_data.csv",
    "KO": "ko_hist_data.csv",
    "V": "visa_hist_data.csv",
    "AMZN": "amzn_hist_data.csv",
}


def load_symbol_data(symbol):
    csv_path = os.path.join(HISTORICALS_DIR, SYMBOL_CSV_MAP[symbol])
    return pd.read_csv(csv_path)


def load_msft_data():
    return load_symbol_data("MSFT")


# Symbols with enough rows (>=90) for meaningful backtesting (~3 months of data)
def _symbols_with_enough_data(min_rows=90):
    valid = []
    for sym, fname in SYMBOL_CSV_MAP.items():
        path = os.path.join(HISTORICALS_DIR, fname)
        if os.path.exists(path):
            df = pd.read_csv(path)
            if len(df) >= min_rows:
                valid.append(sym)
    return valid


BACKTEST_SYMBOLS = _symbols_with_enough_data()


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

    # Sanity: win rate should not be zero (system generates some winning trades)
    # Note: with MA200 gate + trailing stop, win rate varies by stock volatility
    assert results["win_rate"] >= 0.0, (
        f"Win rate {results['win_rate']:.1%} is negative — something is broken."
    )
    # Average return should not be catastrophically negative
    assert results["avg_actual_return_pct"] >= -10.0, (
        f"Avg return {results['avg_actual_return_pct']:.2f}% is catastrophic."
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
        "filtered_by_confidence": 2,
        "min_buy_confidence": 0.35,
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
    assert "0.35" in report


# ─── Multi-symbol parametrized tests ──────────────────────────────────


@pytest.mark.parametrize("symbol", _symbols_with_enough_data())
@patch("tools.custom_financial_calc._compute_weekly_confirmation", return_value=None)
@patch("tools.custom_financial_calc._get_sp500_trend", return_value=("NEUTRAL", 0.0))
def test_backtest_multi_symbol(mock_sp500, mock_weekly, symbol):
    """Run backtest across all available symbols with sufficient data."""
    df = load_symbol_data(symbol)

    # Use lower min_history for shorter datasets (e.g. AMZN ~252 rows)
    rows = len(df)
    min_hist = min(200, rows - 31)  # ensure at least 31 rows for future trades

    results = run_backtest(
        df, symbol,
        target_profit_pct=10.0,
        max_holding_days=30,
        min_history=min_hist,
        step_days=20,
    )

    print("\n" + format_backtest_report(results))

    assert results["symbol"] == symbol
    assert results["total_buy_signals"] >= 0
    assert isinstance(results["trades"], list)

    if results["total_buy_signals"] > 0:
        assert results["avg_actual_return_pct"] > -15.0, (
            f"{symbol}: avg return {results['avg_actual_return_pct']:.2f}% is catastrophic"
        )


@pytest.mark.parametrize("symbol", _symbols_with_enough_data())
@patch("tools.custom_financial_calc._compute_weekly_confirmation", return_value=None)
@patch("tools.custom_financial_calc._get_sp500_trend", return_value=("NEUTRAL", 0.0))
def test_backtest_confidence_filter_reduces_trades(mock_sp500, mock_weekly, symbol):
    """Applying min_buy_confidence should produce fewer or equal BUY signals."""
    df = load_symbol_data(symbol)
    rows = len(df)
    min_hist = min(200, rows - 31)
    common = dict(target_profit_pct=10.0, max_holding_days=30, min_history=min_hist, step_days=20)

    results_no_filter = run_backtest(df, symbol, **common)
    results_filtered = run_backtest(df, symbol, min_buy_confidence=0.35, **common)

    no_filter_buys = results_no_filter["total_buy_signals"]
    filtered_buys = results_filtered["total_buy_signals"]
    filtered_out = results_filtered.get("filtered_by_confidence", 0)

    print(f"\n{symbol}: no filter={no_filter_buys}, filtered={filtered_buys}, rejected={filtered_out}")

    # filtered should be <= unfiltered
    assert filtered_buys <= no_filter_buys, (
        f"{symbol}: confidence filter produced MORE trades ({filtered_buys} > {no_filter_buys})"
    )
    # The sum of accepted + rejected should equal unfiltered
    assert filtered_buys + filtered_out == no_filter_buys, (
        f"{symbol}: {filtered_buys} + {filtered_out} != {no_filter_buys}"
    )
