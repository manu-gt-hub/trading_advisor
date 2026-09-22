"""
Integration tests for Google Drive handler.
These tests require real credentials and are excluded from the default test suite.
Run manually with: python -m pytest test/test_google_handler.py -v
"""
import os
import json
import pandas as pd
from dotenv import dotenv_values
import pytest
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))

# Guard: skip entire module if google packages are not installed
google_handler = pytest.importorskip("google_handler", reason="google.oauth2 not installed")

# Get absolute path to the env path
current_dir = os.path.dirname(__file__)
path = os.path.join(current_dir, '..', '.env')
env_path = os.path.abspath(path)

def test_get_drive_service_real():
    """
    Real test connecting to Google Drive service using real credentials from .env.
    """
    # Reload .env on every run
    if os.getenv("GITHUB_ACTIONS") != "true":
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env"))
        env = dotenv_values(env_path)
        os.environ.update(env)

    os.environ["GDRIVE_CREDENTIALS_JSON"] = os.environ.get("GDRIVE_CREDENTIALS_JSON", "")
    os.environ["GDRIVE_FILE_ID"] = os.environ.get("GDRIVE_FILE_ID", "")

    assert os.environ["GDRIVE_CREDENTIALS_JSON"], "GDRIVE_CREDENTIALS_JSON is not set"
    assert os.environ["GDRIVE_FILE_ID"], "GDRIVE_FILE_ID is not set"

    service = google_handler.get_drive_service()
    files_list = service.files().list(pageSize=1).execute()

    assert "files" in files_list


def test_load_data_real():
    """
    Real test loading CSV data from Google Drive using real credentials from .env.
    """
    env = dotenv_values(env_path)
    os.environ["GDRIVE_CREDENTIALS_JSON"] = os.environ.get("GDRIVE_CREDENTIALS_JSON", "")
    transactions_id = os.environ["GDRIVE_FILE_ID"] = os.environ.get("GDRIVE_FILE_ID", "")
    buy_file_id = os.environ["BUY_RECOMMENDATIONS_ID"] = os.environ.get("BUY_RECOMMENDATIONS_ID", "")

    assert os.environ["GDRIVE_CREDENTIALS_JSON"], "GDRIVE_CREDENTIALS_JSON is not set"
    assert os.environ["GDRIVE_FILE_ID"], "GDRIVE_FILE_ID is not set"
    assert os.environ["BUY_RECOMMENDATIONS_ID"], "BUY_RECOMMENDATIONS_ID is not set"

    transactions_df = google_handler.load_data(transactions_id)
    assert isinstance(transactions_df, pd.DataFrame)

    df_buy = google_handler.load_data(buy_file_id)
    assert isinstance(df_buy, pd.DataFrame)


def test_update_transactions():
    # Simulate today's date
    today = datetime.today().date()
    # Simulate a buy date 10 days ago
    buy_date = today - timedelta(days=10)

    # Mock analysis dataframe (df_analysis)
    df_analysis = pd.DataFrame({
        'symbol': ['AAPL', 'AMD'],
        'current_price': [165.0, 145.0],  # AAPL has reached the target, AMD has not
        'change_percent': [-0.5, -1.2],
        'manual_financial_analysis': ['✋ HOLD', '❌ SELL'],
        'trading_view_opinion': ['BUY (10) - SELL (5)', 'SELL (12) - NEUTRAL (6)'],
        'llm_opinion': ['sell...', 'sell...'],
        'action': ['HOLD', 'SELL']
    })
    

    # Mock transactions dataframe (df_transactions)
    df_transactions = pd.DataFrame({
        'symbol': ['AAPL', 'AMD'],
        'buy_value': [150.0, 140.0],
        'buy_date': [buy_date, buy_date],
        'sell_value': [None, None],
        'sell_date': [None, None],
        'buy_sell_days_diff': [None, None],
        'percentage_benefit': [None, None],
    })

    # Set target profit (10%)
    revenue_percentage = 10  

    # Call the function
    updated_df = google_handler.update_transactions(df_analysis, df_transactions, revenue_percentage)

    # Validate AAPL was updated (165 >= 150 * 1.1 = 165)
    aapl_row = updated_df[updated_df['symbol'] == 'AAPL'].iloc[0]
    assert aapl_row['sell_value'] == 165.0, "AAPL sell_value should be updated"
    assert aapl_row['sell_date'] == today.isoformat(), "AAPL sell_date should be today"
    assert aapl_row['buy_sell_days_diff'] == 10, "AAPL days diff should be 10"
    assert round(aapl_row['percentage_benefit'], 2) == 10.0, "AAPL should have 10% benefit"

    # Validate AMD was not updated (145 < 140 * 1.1 = 154)
    amd_row = updated_df[updated_df['symbol'] == 'AMD'].iloc[0]
    assert pd.isna(amd_row['sell_value']), "AMD sell_value should not be updated"
    assert pd.isna(amd_row['sell_date']), "AMD sell_date should not be updated"
    assert pd.isna(amd_row['buy_sell_days_diff']), "AMD days diff should not be updated"
    assert pd.isna(amd_row['percentage_benefit']), "AMD percentage_benefit should not be updated"


def test_update_transactions_repairs_partially_closed_row():
    """
    Regression test: a row with sell_value set but missing sell_date,
    buy_sell_days_diff and percentage_benefit should be repaired.
    """
    today = datetime.today().date()
    buy_date = today - timedelta(days=30)

    df_analysis = pd.DataFrame({
        'symbol': ['AAPL'],
        'current_price': [166.0],
    })

    # Row was partially saved: sell_value exists, but metadata is missing
    df_transactions = pd.DataFrame({
        'symbol': ['AAPL'],
        'buy_value': [150.0],
        'buy_date': [buy_date],
        'sell_value': [165.0],
        'sell_date': [None],
        'buy_sell_days_diff': [None],
        'percentage_benefit': [None],
    })

    updated_df = google_handler.update_transactions(df_analysis, df_transactions, 10)

    aapl_row = updated_df[updated_df['symbol'] == 'AAPL'].iloc[0]
    assert aapl_row['sell_value'] == 165.0, "sell_value should be preserved"
    assert aapl_row['sell_date'] == today.isoformat(), "sell_date should be repaired"
    assert aapl_row['buy_sell_days_diff'] == 30, "days diff should be repaired"
    assert round(aapl_row['percentage_benefit'], 2) == 10.0, "percentage benefit should be repaired"


def test_update_transactions_respects_revenue_percentage_over_take_profit():
    """
    Regression test: when take_profit (ATR-based) is lower than the revenue
    target, the sell must record target_price as exit price so that
    revenue_percentage is respected.
    Example: buy=100, revenue_percentage=10 → target=110, but take_profit=106
    (ATR was small). The sell triggers at current_price=111 (>=110) and must
    record exit_price=110 (10%), not 106 (6%).
    """
    today = datetime.today().date()
    buy_date = today - timedelta(days=15)

    df_analysis = pd.DataFrame({
        'symbol': ['AAPL'],
        'current_price': [111.0],  # above target (110) → triggers sell
    })

    df_transactions = pd.DataFrame({
        'symbol': ['AAPL'],
        'buy_value': [100.0],
        'buy_date': [buy_date],
        'sell_value': [None],
        'sell_date': [None],
        'buy_sell_days_diff': [None],
        'percentage_benefit': [None],
        'stop_loss': [96.0],
        'take_profit': [106.0],  # ATR-based, lower than target (110)
    })

    updated_df = google_handler.update_transactions(df_analysis, df_transactions, 10)

    aapl_row = updated_df[updated_df['symbol'] == 'AAPL'].iloc[0]
    # exit_price must be target_price (110), not take_profit (106)
    assert aapl_row['sell_value'] == 110.0, (
        f"sell_value should be target_price=110.0, got {aapl_row['sell_value']}"
    )
    assert round(aapl_row['percentage_benefit'], 2) == 10.0, (
        f"percentage_benefit should be 10.0%, got {aapl_row['percentage_benefit']}"
    )


def test_update_transactions_repairs_blank_string_sell_date():
    """
    Regression test: Google Sheets sometimes exports missing cells as empty strings
    instead of NaN. The repair path must handle that.
    """
    today = datetime.today().date()
    buy_date = today - timedelta(days=10)

    df_analysis = pd.DataFrame({
        'symbol': ['AAPL'],
        'current_price': [160.0],
    })

    df_transactions = pd.DataFrame({
        'symbol': ['AAPL'],
        'buy_value': [150.0],
        'buy_date': [buy_date],
        'sell_value': [165.0],
        'sell_date': [''],  # Blank string from Google Sheets
        'buy_sell_days_diff': [''],
        'percentage_benefit': [''],
    })

    updated_df = google_handler.update_transactions(df_analysis, df_transactions, 10)

    aapl_row = updated_df[updated_df['symbol'] == 'AAPL'].iloc[0]
    assert aapl_row['sell_value'] == 165.0
    assert aapl_row['sell_date'] == today.isoformat()
    assert aapl_row['buy_sell_days_diff'] == 10
    assert round(aapl_row['percentage_benefit'], 2) == 10.0


@patch("tools.finnhub_client.get_quote")
def test_update_transactions_fetches_live_price_for_missing_symbol(mock_get_quote):
    """
    When a symbol has an open transaction but is NOT in the current analysis run,
    update_transactions should fetch the live price via Finnhub and still close
    the transaction if target is reached.
    """
    today = datetime.today().date()
    buy_date = today - timedelta(days=20)

    # Analysis has only AMD — AAPL is missing (not in SYMBOLS_INTEREST_LIST this run)
    df_analysis = pd.DataFrame({
        'symbol': ['AMD'],
        'current_price': [145.0],
    })

    # AAPL has an open transaction with buy_value=307.14, should sell at 10% target
    df_transactions = pd.DataFrame({
        'symbol': ['AAPL', 'AMD'],
        'buy_value': [307.14, 140.0],
        'buy_date': [buy_date, buy_date],
        'sell_value': [None, None],
        'sell_date': [None, None],
        'buy_sell_days_diff': [None, None],
        'percentage_benefit': [None, None],
    })

    # Mock Finnhub to return a price of 340 for AAPL (above 10% target = 337.85)
    mock_get_quote.return_value = {"c": 340.0}

    updated_df = google_handler.update_transactions(df_analysis, df_transactions, 10)

    aapl_row = updated_df[updated_df['symbol'] == 'AAPL'].iloc[0]
    expected_target = round(307.14 * 1.10, 2)  # 337.85
    assert aapl_row['sell_value'] == expected_target, (
        f"AAPL should be sold at target price {expected_target}, got {aapl_row['sell_value']}"
    )
    assert aapl_row['sell_date'] == today.isoformat()
    assert round(aapl_row['percentage_benefit'], 2) == 10.0

    # AMD should not be sold (145 < 154)
    amd_row = updated_df[updated_df['symbol'] == 'AMD'].iloc[0]
    assert pd.isna(amd_row['sell_value'])

