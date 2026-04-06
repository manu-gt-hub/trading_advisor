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
    extract_custom_confidence,
    apply_technical_filter,
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

    # One is None or error — single valid LLM, no custom
    assert decide_final_action(None, 'BUY') == 'BUY'
    assert decide_final_action('SELL', None) == 'SELL'
    assert decide_final_action('error', 'HOLD') == 'HOLD'
    assert decide_final_action('BUY', 'error') == 'BUY'
    assert decide_final_action(None, 'error') == 'EMPTY_DECISION'
    assert decide_final_action('error', None) == 'EMPTY_DECISION'

    # Both different and valid — conservative logic
    assert decide_final_action('BUY', 'SELL') == 'HOLD'   # BUY vs SELL → conservative HOLD
    assert decide_final_action('SELL', 'HOLD') == 'SELL'   # SELL vs HOLD → risk mgmt SELL
    assert decide_final_action('HOLD', 'BUY') == 'HOLD'    # HOLD vs BUY → conservative HOLD

    # Both None or error
    assert decide_final_action(None, None) == 'EMPTY_DECISION'
    assert decide_final_action('error', 'error') == 'EMPTY_DECISION'
    assert decide_final_action(None, 'error') == 'EMPTY_DECISION'


def test_decide_final_action_with_custom_tiebreaker():
    # Custom breaks tie when LLMs disagree
    assert decide_final_action('BUY', 'SELL', custom_decision='BUY') == 'BUY'
    assert decide_final_action('BUY', 'SELL', custom_decision='SELL') == 'SELL'
    assert decide_final_action('BUY', 'HOLD', custom_decision='HOLD') == 'HOLD'
    assert decide_final_action('SELL', 'HOLD', custom_decision='SELL') == 'SELL'

    # Custom disagrees with both LLMs: use custom only if high confidence
    assert decide_final_action('BUY', 'HOLD', custom_decision='SELL', custom_confidence=0.5) == 'SELL'
    assert decide_final_action('BUY', 'HOLD', custom_decision='SELL', custom_confidence=0.2) == 'HOLD'

    # No valid LLMs, fall back to custom
    assert decide_final_action(None, 'error', custom_decision='BUY') == 'BUY'
    assert decide_final_action('error', None, custom_decision='SELL') == 'SELL'

    # Single LLM + custom disagree → conservative HOLD
    assert decide_final_action('BUY', None, custom_decision='SELL') == 'HOLD'
    # Single LLM + custom agree on SELL → SELL
    assert decide_final_action('SELL', None, custom_decision='SELL') == 'SELL'




# Test: generate_action_column (default logic)
def test_generate_action_column_default():
    df_test = pd.DataFrame(test_data)
    df_result = generate_action_column(df_test.copy(), "DEFAULT")

    expected = ['SELL', 'BUY', 'SELL', 'HOLD', 'EMPTY_DECISION']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[DEFAULT] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"

# Test: extract_custom_confidence
def test_extract_custom_confidence():
    assert extract_custom_confidence('0.45 BUY') == 0.45
    assert extract_custom_confidence('-0.30 SELL') == -0.30
    assert extract_custom_confidence('0.00 HOLD') == 0.0
    assert extract_custom_confidence(None) == 0.0
    assert extract_custom_confidence('invalid') == 0.0
    assert extract_custom_confidence(123) == 0.0


# Test: apply_technical_filter
def test_apply_technical_filter():
    # LLM BUY, technical SELL with conf >= 0.3 → vetoed to HOLD
    assert apply_technical_filter('BUY', '0.35 SELL') == 'HOLD'
    # LLM BUY, technical SELL with low conf → trust LLM
    assert apply_technical_filter('BUY', '0.20 SELL') == 'BUY'
    # LLM BUY, technical HOLD with conf >= 0.4 → vetoed to HOLD
    assert apply_technical_filter('BUY', '0.50 HOLD') == 'HOLD'
    # LLM BUY, technical HOLD with low conf → trust LLM
    assert apply_technical_filter('BUY', '0.30 HOLD') == 'BUY'
    # LLM BUY, technical BUY → trust LLM (agreement)
    assert apply_technical_filter('BUY', '0.60 BUY') == 'BUY'
    # LLM SELL, technical BUY with conf >= 0.5 → softened to HOLD
    assert apply_technical_filter('SELL', '0.55 BUY') == 'HOLD'
    # LLM SELL, technical BUY with low conf → trust LLM
    assert apply_technical_filter('SELL', '0.30 BUY') == 'SELL'
    # LLM SELL, technical SELL → trust LLM (agreement)
    assert apply_technical_filter('SELL', '0.80 SELL') == 'SELL'
    # LLM HOLD → always trust HOLD (no filter needed)
    assert apply_technical_filter('HOLD', '0.80 BUY') == 'HOLD'
    # Error LLM decision → pass through
    assert apply_technical_filter(None, '0.50 BUY') is None
    # No custom data → trust LLM
    assert apply_technical_filter('BUY', None) == 'BUY'


# Test: generate_action_column with force_opinion = LLM1 (no technical filter)
def test_generate_action_column_force_llm():
    df_test = pd.DataFrame(test_data)
    df_result = generate_action_column(df_test.copy(), opinion_type="LLM1")

    # Without manual_financial_analysis column, no filter is applied
    expected = ['SELL', 'BUY', 'EMPTY_DECISION', 'SELL', 'EMPTY_DECISION']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[LLM] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"


# Test: generate_action_column with force_opinion = LLM1 + technical filter
def test_generate_action_column_force_llm_with_filter():
    df_test = pd.DataFrame({
        'symbol': ['AAPL', 'MSFT', 'GOOGL', 'AMZN'],
        'llm_opinion': [
            'BUY - Strong momentum.',           # BUY, technical SELL high conf → HOLD
            'BUY - All indicators up.',          # BUY, technical BUY → BUY
            'SELL - Bearish trend.',              # SELL, technical BUY high conf → HOLD
            'SELL - Weak momentum.',              # SELL, technical SELL → SELL
        ],
        'manual_financial_analysis': [
            '0.40 SELL',   # vetoes BUY
            '0.60 BUY',    # confirms BUY
            '0.55 BUY',    # softens SELL
            '0.70 SELL',   # confirms SELL
        ],
    })
    df_result = generate_action_column(df_test.copy(), opinion_type="LLM1")

    expected = ['HOLD', 'BUY', 'HOLD', 'SELL']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[LLM1+filter] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"

# Test: generate_action_column with force_opinion = LLM2
def test_generate_action_column_force_llm_2():
    df_test = pd.DataFrame(test_data)
    df_result = generate_action_column(df_test.copy(), opinion_type="LLM2")

    expected = ['SELL', 'BUY', 'SELL', 'BUY', 'EMPTY_DECISION']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[LLM2] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"

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
