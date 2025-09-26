import pandas as pd
import re
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from general import decide_final_action, extract_llm_decision,extract_trading_view_decision,generate_decision_column

# Sample test data
test_data = {
    'trading_view_opinion': [
        'SELL (9) - Neutral (8) - Buy (7)',      # SELL
        'SELL (6) - NEUTRAL (8) - BUY (9)',      # BUY
        'SELL (8) - NEUTRAL (8) - BUY (8)',      # SELL (tie, first)
        'BUY (10) - Neutral (5) - SELL (2)',     # BUY
        'NEUTRAL (9) - SELL (5) - BUY (5)',      # NEUTRAL
    ],
    'llm_opinion': [
        'sell - Price is below moving averages.',       # match SELL
        'buy - All indicators show upward movement.',   # match BUY
        'neutral - No strong signals detected.',         # mismatch with SELL
        'sell - Momentum weakening, risk of reversal.',  # mismatch with BUY
        'neutral - Sideways market, no clear signal.',   # match NEUTRAL
    ]
}

def test_extract_trading_view_decision():
    assert extract_trading_view_decision('SELL (9) - Neutral (8) - Buy (7)') == 'SELL'
    assert extract_trading_view_decision('SELL (6) - NEUTRAL (8) - BUY (9)') == 'BUY'
    assert extract_trading_view_decision('SELL (8) - NEUTRAL (8) - BUY (8)') == 'SELL'  # tie, picks first
    assert extract_trading_view_decision('BUY (10) - Neutral (5) - SELL (2)') == 'BUY'
    assert extract_trading_view_decision('NEUTRAL (9) - SELL (5) - BUY (5)') == 'NEUTRAL'
    assert extract_trading_view_decision('Invalid string with no numbers') is None
    assert extract_trading_view_decision('') is None


def test_extract_llm_decision():
    assert extract_llm_decision('sell - Something something') == 'SELL'
    assert extract_llm_decision('buy - More text here') == 'BUY'
    assert extract_llm_decision('neutral - Sideways trend') == 'NEUTRAL'
    assert extract_llm_decision('SELL- No space') == 'SELL'
    assert extract_llm_decision('   buy -  Extra spaces   ') == 'BUY'
    assert extract_llm_decision(None) is None
    assert extract_llm_decision('') == ''


def test_decide_final_action():
    assert decide_final_action('SELL', 'SELL') == 'SELL'
    assert decide_final_action('BUY', 'BUY') == 'BUY'
    assert decide_final_action('NEUTRAL', 'NEUTRAL') == 'NEUTRAL'
    assert decide_final_action('SELL', 'BUY') == 'HOLD'
    assert decide_final_action('BUY', 'NEUTRAL') == 'HOLD'
    assert decide_final_action('SELL', None) == 'HOLD'
    assert decide_final_action(None, 'BUY') == 'HOLD'
    assert decide_final_action(None, None) == 'HOLD'

def test_generate_decision_column():
    
    expected_decisions = ['SELL', 'BUY', 'HOLD', 'HOLD', 'NEUTRAL']

    # Create DataFrame
    df_test = pd.DataFrame(test_data)

    # Apply the function
    df_result = generate_decision_column(df_test)

    # Validate each result
    for i, expected in enumerate(expected_decisions):
        result = df_result.loc[i, 'decision']
        assert result == expected, f"Test failed at index {i}: expected {expected}, got {result}"

