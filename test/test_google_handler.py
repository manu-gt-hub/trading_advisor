import os
import json
import pandas as pd
from dotenv import dotenv_values
import pytest
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from google_handler import get_drive_service, load_data, update_transactions

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

    service = get_drive_service()
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

    transactions_df = load_data(transactions_id)
    assert isinstance(transactions_df, pd.DataFrame)

    df_buy = load_data(buy_file_id)
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
        'decision': ['HOLD', 'SELL']
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
    from datetime import date
    updated_df = update_transactions(df_analysis, df_transactions, revenue_percentage)

    # Validate AAPL was updated (165 >= 150 * 1.1 = 165)
    aapl_row = updated_df[updated_df['symbol'] == 'AAPL'].iloc[0]
    assert aapl_row['sell_value'] == 165.0, "AAPL sell_value should be updated"
    assert aapl_row['sell_date'] == today, "AAPL sell_date should be today"
    assert aapl_row['buy_sell_days_diff'] == 10, "AAPL days diff should be 10"
    assert round(aapl_row['percentage_benefit'], 2) == 10.0, "AAPL should have 10% benefit"

    # Validate AMD was not updated (145 < 140 * 1.1 = 154)
    amd_row = updated_df[updated_df['symbol'] == 'AMD'].iloc[0]
    assert pd.isna(amd_row['sell_value']), "AMD sell_value should not be updated"
    assert pd.isna(amd_row['sell_date']), "AMD sell_date should not be updated"
    assert pd.isna(amd_row['buy_sell_days_diff']), "AMD days diff should not be updated"
    assert pd.isna(amd_row['percentage_benefit']), "AMD percentage_benefit should not be updated"

