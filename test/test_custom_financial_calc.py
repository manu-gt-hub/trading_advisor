import sys
import os
import pytest
import pandas as pd
from datetime import datetime, timedelta
from tempfile import NamedTemporaryFile
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from custom_financial_calc import review_transactions, evaluate_buy_interest

# Get revenue percentage from environment variable or use a default (e.g. 10%)
REVENUE_PERCENTAGE = float(os.environ.get("REVENUE_PERCENTAGE", 20.0))


def create_mock_transaction_file(buy_price=100.0, symbol="AAPL"):
    """Helper to create a temporary CSV file with a mock open transaction."""
    tmp_file = NamedTemporaryFile(delete=False, mode='w', suffix=".csv")
    df = pd.DataFrame([{
        "symbol": symbol,
        "buy_date": (datetime.today() - timedelta(days=10)).strftime('%Y-%m-%d'),
        "current_price": buy_price,
        "sell_date": "",
        "sell_value": "",
        "buy_sell_days_diff": "",
        "percentage_benefit": ""
    }])
    df.to_csv(tmp_file.name, index=False)
    return tmp_file.name


def test_review_transactions_success_case():
    """Should close the transaction if the gain exceeds REVENUE_PERCENTAGE."""
    file_path = create_mock_transaction_file(buy_price=100.0)
    gain = 1 + (REVENUE_PERCENTAGE / 100)
    current_df = pd.DataFrame([{"symbol": "AAPL", "current_price": 100.0 * gain}])

    updated = review_transactions(file_path, current_df, revenue_percentage=REVENUE_PERCENTAGE)

    assert not updated.empty
    row = updated.iloc[0]
    assert row["symbol"] == "AAPL"
    assert float(row["sell_value"]) == pytest.approx(100.0 * gain, rel=1e-2)
    assert float(row["percentage_benefit"]) >= REVENUE_PERCENTAGE
    assert pd.notna(row["sell_date"])

    os.remove(file_path)


def test_review_transactions_no_update():
    """Should not close the transaction if gain is below REVENUE_PERCENTAGE."""
    file_path = create_mock_transaction_file(buy_price=100.0)
    # Slightly under the required gain
    current_df = pd.DataFrame([{"symbol": "AAPL", "current_price": 100.0 * (1 + (REVENUE_PERCENTAGE - 2) / 100)}])

    updated = review_transactions(file_path, current_df, revenue_percentage=REVENUE_PERCENTAGE)

    assert updated.empty

    os.remove(file_path)


def test_review_transactions_invalid_price():
    """Should skip rows where current_price is not a valid number."""
    file_path = create_mock_transaction_file(buy_price=100.0)
    current_df = pd.DataFrame([{"symbol": "AAPL", "current_price": "not_a_number"}])

    updated = review_transactions(file_path, current_df, revenue_percentage=REVENUE_PERCENTAGE)

    assert updated.empty

    os.remove(file_path)


def test_evaluate_buy_interest_valid_data():
    """Basic test of evaluation function with valid trend data."""
    dates = pd.date_range(end=datetime.today(), periods=250)
    prices = [100 + i * 0.2 for i in range(250)]  # upward trend
    df = pd.DataFrame({"date": dates, "close": prices})
    current_price = df["close"].iloc[-1]

    result = evaluate_buy_interest("TEST", df, current_price)

    assert isinstance(result, dict)
    assert result["symbol"] == "TEST"
    assert result["evaluation"] in ["✅ BUY", "❌ SELL", "✋ HOLD"]
    assert isinstance(result["active_signals"], list)
    assert isinstance(result["signals"], dict)


def test_evaluate_buy_interest_invalid_data():
    """Check how the function handles invalid historical data."""
    df = pd.DataFrame({"date": ["invalid", "also bad"], "close": ["bad", "worse"]})
    result = evaluate_buy_interest("BROKEN", df, 100.0)

    assert result["evaluation"] == "⚠️ Evaluation failed"
    assert "error" in result["signals"]
    assert result["active_signals"] == ["failed"]
