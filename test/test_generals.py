import pandas as pd
import numpy as np
import re
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
# Import all the necessary functions from your script
from general import (
    extract_trading_view_decision,
    extract_llm_decision,
    extract_custom_decision,
    decide_final_action,
    generate_action_column,
    add_urls_column
)

# Sample test data
test_data = {
    'symbol': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'],
    'llm_2_opinion': [
        'SELL - Price is below moving averages.',     # SELL
        'BUY - All indicators show upward movement.',      # BUY
        'SELL - Price is below moving averages.',       # SELL (tie, picks first)
        'BUY - All indicators show upward movement.',     # BUY
        'EMPTY_DECISION - Sideways market, no clear signal.',     # NEUTRAL
    ],
    'llm_opinion': [
        'SELL - Price is below moving averages.',
        'BUY - All indicators show upward movement.',
        'EMPTY_DECISION - No strong signals detected.',
        'SELL - Momentum weakening, risk of reversal.',
        'EMPTY_DECISION - Sideways market, no clear signal.',
    ]
}

# Test: extract_trading_view_decision
def test_extract_trading_view_decision():
    assert extract_trading_view_decision('SELL (9) - Neutral (8) - Buy (7)') == 'SELL'
    assert extract_trading_view_decision('SELL (6) - NEUTRAL (8) - BUY (9)') == 'BUY'
    assert extract_trading_view_decision('SELL (8) - NEUTRAL (8) - BUY (8)') == 'SELL'
    assert extract_trading_view_decision('BUY (10) - Neutral (5) - SELL (2)') == 'BUY'
    assert extract_trading_view_decision('NEUTRAL (9) - SELL (5) - BUY (5)') == 'NEUTRAL'
    assert extract_trading_view_decision('Invalid string with no numbers') is None
    assert extract_trading_view_decision('') is None
    assert extract_trading_view_decision(None) == "error"

# Test: extract_llm_decision
def test_extract_llm_decision():
    assert extract_llm_decision('sell - Something something') == 'SELL'
    assert extract_llm_decision('buy - More text here') == 'BUY'
    assert extract_llm_decision('neutral - Sideways trend') == 'NEUTRAL'
    assert extract_llm_decision('SELL- No space') == 'SELL'
    assert extract_llm_decision('   buy -  Extra spaces   ') == 'BUY'
    assert extract_llm_decision(None) is None
    assert extract_llm_decision('') == ''


# Test: decide_final_action
def test_decide_final_action():
    # Both equal
    assert decide_final_action('BUY', 'BUY') == 'BUY'
    assert decide_final_action('SELL', 'SELL') == 'SELL'
    assert decide_final_action('HOLD', 'HOLD') == 'HOLD'

    # One is None or error
    assert decide_final_action(None, 'BUY') == 'BUY'
    assert decide_final_action('SELL', None) == 'SELL'
    assert decide_final_action('error', 'HOLD') == 'HOLD'
    assert decide_final_action('BUY', 'error') == 'BUY'
    assert decide_final_action(None, 'error') == 'EMPTY_DECISION'
    assert decide_final_action('error', None) == 'EMPTY_DECISION'

    # Both different and valid
    assert decide_final_action('BUY', 'SELL') == 'EMPTY_DECISION'
    assert decide_final_action('SELL', 'HOLD') == 'EMPTY_DECISION'
    assert decide_final_action('HOLD', 'BUY') == 'EMPTY_DECISION'

    # Both None or error
    assert decide_final_action(None, None) == 'EMPTY_DECISION'
    assert decide_final_action('error', 'error') == 'EMPTY_DECISION'
    assert decide_final_action(None, 'error') == 'EMPTY_DECISION'




# Test: generate_action_column (default logic)
def test_generate_action_column_default():
    df_test = pd.DataFrame(test_data)
    df_result = generate_action_column(df_test.copy(), "DEFAULT")

    expected = ['SELL', 'BUY', 'EMPTY_DECISION', 'EMPTY_DECISION', 'EMPTY_DECISION']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[DEFAULT] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"

# Test: generate_action_column with force_opinion = LLM1
def test_generate_action_column_force_llm():
    df_test = pd.DataFrame(test_data)
    df_result = generate_action_column(df_test.copy(), opinion_type="LLM1")

    expected = ['SELL', 'BUY', 'EMPTY_DECISION', 'SELL', 'EMPTY_DECISION']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[LLM] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"

# Test: generate_action_column with force_opinion = LLM2
def test_generate_action_column_force_llm_2():
    df_test = pd.DataFrame(test_data)
    df_result = generate_action_column(df_test.copy(), opinion_type="LLM2")

    expected = ['SELL', 'BUY', 'SELL', 'BUY', 'EMPTY_DECISION']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[LLM2] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"

import pandas as pd
from datetime import datetime

import pandas as pd

import pandas as pd

def test_add_urls_column_builds_tradingview_urls_correctly():
    # Arrange: create a sample buy DataFrame
    buy_df = pd.DataFrame({
        "symbol": ["NVDA", "RHM.DE", "KO", "UNKNOWN", None],
        "buy_value": [500, 300, 60, 10, 20],
    })

    # Act: apply the function under test
    result_df = add_urls_column(buy_df)

    # Assert: the new column exists
    assert "tradingview_url" in result_df.columns

    # Assert: the new column is the last one
    assert result_df.columns[-1] == "tradingview_url"

    # Assert: valid symbols generate correct TradingView URLs
    assert (
        result_df.loc[0, "tradingview_url"]
        == "https://en.tradingview.com/symbols/NASDAQ-NVDA/technicals/"
    )

    assert (
        result_df.loc[1, "tradingview_url"]
        == "https://en.tradingview.com/symbols/XETR-RHM/technicals/"
    )

    assert (
        result_df.loc[2, "tradingview_url"]
        == "https://en.tradingview.com/symbols/NYSE-KO/technicals/"
    )

    # Assert: unknown or invalid symbols return "NOT FOUND"
    assert result_df.loc[3, "tradingview_url"] == "NOT FOUND"
    assert result_df.loc[4, "tradingview_url"] == "NOT FOUND"
