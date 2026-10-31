import sys
import os
import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import patch
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from tools.custom_financial_calc import evaluate_buy_interest

# Utility function to load historical data from CSV
def load_hist_data():
    current_dir = os.path.dirname(__file__)
    csv_path = os.path.join(current_dir, '..', 'resources', 'historicals', 'msft_hist_data.csv')
    return pd.read_csv(csv_path)

@patch("tools.custom_financial_calc._compute_weekly_confirmation", return_value=None)
@patch("tools.custom_financial_calc._get_sp500_trend", return_value=("BULLISH", 1.5))
def test_evaluate_buy_interest_returns_expected_structure(mock_sp500, mock_weekly):
    df = load_hist_data()
    current_price = df['close'].iloc[-1]  # Latest close as current price

    result = evaluate_buy_interest("MSFT", df, current_price)

    # Basic asserts about the structure and keys
    assert result["symbol"] == "MSFT"

    # evaluation should now be in lowercase
    assert result["evaluation"] in ["BUY", "SELL", "HOLD", "EVALUATION_FAILED"]

    # Confidence score should be a float between -1 and 1
    assert isinstance(result["confidence"], float)
    assert -1.0 <= result["confidence"] <= 1.0

    # Active signals should be a list
    assert isinstance(result["active_signals"], list)
    assert all(isinstance(sig, str) for sig in result["active_signals"])

    # Signals should be a dictionary with expected keys
    assert isinstance(result["signals"], dict)
    for key in [
        "SMA_50",
        "SMA_200",
        "RSI",
        "MACD",
        "MACD_Signal",
        "MACD_Hist",
        "MA50_Slope",
        "ROC_10",
        "Volatility_20",
        "ATR_14",
        "Breakout_20",
        "Monthly_10pct_Prob",
        "Current_Price",
        "EMA_20",
        "MACD_Hist_Slope",
        "BB_Upper",
        "BB_Lower",
        "ADX",
        "Plus_DI",
        "Minus_DI",
        "Stoch_RSI_K",
        "Stoch_RSI_D",
        "Fib_382",
        "Fib_500",
        "Fib_618",
        "Market_Trend",
    ]:
        assert key in result["signals"], f"Missing signal key: {key}"

    # Sanity check: Current_Price should match the input
    assert round(result["signals"]["Current_Price"], 2) == round(current_price, 2)


@patch("tools.custom_financial_calc._compute_weekly_confirmation", return_value=None)
@patch("tools.custom_financial_calc._get_sp500_trend", return_value=("BULLISH", 1.5))
def test_evaluate_buy_interest_buy_or_sell_or_hold(mock_sp500, mock_weekly):
    df = load_hist_data()
    current_price = df['close'].iloc[-1]

    result = evaluate_buy_interest("MSFT", df, current_price)
    eval = result["evaluation"]

    # Since data is real-ish, expect one of these
    assert eval in ["BUY", "SELL", "HOLD"]

def test_evaluate_buy_interest_handles_bad_data():

    # Create intentionally bad DataFrame (invalid date and close values)
    bad_df = pd.DataFrame({
        "date": ["not_a_date"],
        "close": ["not_a_number"]
    })
    current_price = 100.0

    # Call the function with bad data
    result = evaluate_buy_interest("MSFT", bad_df, current_price)

    # Assert the function handles the error gracefully
    assert result["evaluation"] == "EVALUATION_FAILED"
    assert result["active_signals"] == ["Evaluation failed due to error."]
    assert "error" in result["signals"]
