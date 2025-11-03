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
    generate_action_column
)

# Sample test data
test_data = {
    'symbol': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'],
    'trading_view_opinion': [
        'SELL (9) - Neutral (8) - Buy (7)',      # SELL
        'SELL (6) - NEUTRAL (8) - BUY (9)',      # BUY
        'SELL (8) - NEUTRAL (8) - BUY (8)',      # SELL (tie, picks first)
        'BUY (10) - Neutral (5) - SELL (2)',     # BUY
        'NEUTRAL (9) - SELL (5) - BUY (5)',      # NEUTRAL
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

# Test: generate_action_column with force_opinion = LLM
def test_generate_action_column_force_llm():
    df_test = pd.DataFrame(test_data)
    df_result = generate_action_column(df_test.copy(), opinion_type="LLM")

    expected = ['SELL', 'BUY', 'EMPTY_DECISION', 'SELL', 'EMPTY_DECISION']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[LLM] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"

# Test: generate_action_column with force_opinion = TV
def test_generate_action_column_force_tv():
    df_test = pd.DataFrame(test_data)
    df_result = generate_action_column(df_test.copy(), opinion_type="TV")

    expected = ['SELL', 'BUY', 'SELL', 'BUY', 'NEUTRAL']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[TV] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"
