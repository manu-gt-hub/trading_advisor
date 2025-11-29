import sys
import os
import pytest
import pandas as pd
from datetime import datetime, timedelta
from tempfile import NamedTemporaryFile
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from tools.custom_financial_calc import review_transactions, evaluate_buy_interest

# Get revenue percentage from environment variable or use a default (e.g. 10%)
REVENUE_PERCENTAGE = float(os.environ.get("REVENUE_PERCENTAGE", 20.0))

# Get absolute path to the CSV relative to this test file
current_dir = os.path.dirname(__file__)
csv_path = os.path.join(current_dir, '..', 'resources', 'transactions.csv')
transactions_csv_path = os.path.abspath(csv_path)

def test_review_transactions():
    # Load mock transactions from CSV
    transactions_df = pd.read_csv(transactions_csv_path, parse_dates=["buy_date", "sell_date"])

    # Simulated current prices for the relevant symbols
    hist_data = pd.DataFrame([
        {"symbol": "AAPL", "current_price": 185.00},   # Should trigger a sale if profit > 5%
        {"symbol": "MSFT", "current_price": 320.00},   # Should also trigger a sale
        {"symbol": "NFLX", "current_price": 405.00},   # Low gain, should NOT trigger
        {"symbol": "NVDA", "current_price": 600.00},   # High gain, should trigger
        {"symbol": "GOOGL", "current_price": 2950.00}, # Already sold, should be ignored
    ])

    # Run the transaction review function
    updated_df = review_transactions(transactions_df.copy(), hist_data, REVENUE_PERCENTAGE)
    # Assert that at least one transaction was updated
    assert not updated_df.empty, "Expected at least one transaction to be closed, but none were"
    # Assert all returned rows have a sell date
    assert all(updated_df["sell_date"].notna()), "Some closed transactions are missing a sell_date"
    # Assert that all closed transactions meet the minimum revenue threshold
    assert all(updated_df["percentage_benefit"] >= REVENUE_PERCENTAGE), "Some closed transactions do not meet the minimum % gain"
    # Check that a specific symbol (e.g., AAPL) was indeed sold
    assert "AAPL" in updated_df["symbol"].values, "Expected AAPL to be closed, but it was not"

# Utility function to load historical data from CSV
def load_hist_data():
    current_dir = os.path.dirname(__file__)
    csv_path = os.path.join(current_dir, '..', 'resources', 'msft_hist_data.csv')
    return pd.read_csv(csv_path)

def test_evaluate_buy_interest_returns_expected_structure():
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
        "Current_Price"
    ]:
        assert key in result["signals"]

    # Sanity check: Current_Price should match the input
    assert round(result["signals"]["Current_Price"], 2) == round(current_price, 2)


def test_evaluate_buy_interest_buy_or_sell_or_hold():
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
