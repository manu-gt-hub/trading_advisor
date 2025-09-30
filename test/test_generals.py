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
    generate_decision_column
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
        'sell - Price is below moving averages.',
        'buy - All indicators show upward movement.',
        'neutral - No strong signals detected.',
        'sell - Momentum weakening, risk of reversal.',
        'neutral - Sideways market, no clear signal.',
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
    assert decide_final_action('SELL', 'SELL') == 'SELL'
    assert decide_final_action('BUY', 'BUY') == 'BUY'
    assert decide_final_action('NEUTRAL', 'NEUTRAL') == 'NEUTRAL'
    assert decide_final_action('SELL', 'BUY') == 'HOLD'
    assert decide_final_action('BUY', 'NEUTRAL') == 'HOLD'
    assert decide_final_action('SELL', None) == 'HOLD'
    assert decide_final_action(None, 'BUY') == 'HOLD'
    assert decide_final_action(None, None) == 'HOLD'

# Test: generate_decision_column (default logic)
def test_generate_decision_column_default():
    df_test = pd.DataFrame(test_data)
    df_result = generate_decision_column(df_test.copy(), "")

    expected = ['SELL', 'BUY', 'HOLD', 'HOLD', 'NEUTRAL']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'decision'] == exp, f"[DEFAULT] Index {i}: expected {exp}, got {df_result.loc[i, 'decision']}"

# Test: generate_decision_column with force_opinion = LLM
def test_generate_decision_column_force_llm():
    df_test = pd.DataFrame(test_data)
    df_result = generate_decision_column(df_test.copy(), opinion_type="LLM")

    expected = ['SELL', 'BUY', 'NEUTRAL', 'SELL', 'NEUTRAL']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'decision'] == exp, f"[LLM] Index {i}: expected {exp}, got {df_result.loc[i, 'decision']}"

# Test: generate_decision_column with force_opinion = TV
def test_generate_decision_column_force_tv():
    df_test = pd.DataFrame(test_data)
    df_result = generate_decision_column(df_test.copy(), opinion_type="TV")

    expected = ['SELL', 'BUY', 'SELL', 'BUY', 'NEUTRAL']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'decision'] == exp, f"[TV] Index {i}: expected {exp}, got {df_result.loc[i, 'decision']}"
