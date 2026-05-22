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
    extract_llm_confidence,
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
    # Old format: "DECISION - explanation"
    assert extract_llm_decision('sell - Something something') == 'SELL'
    assert extract_llm_decision('buy - More text here') == 'BUY'
    assert extract_llm_decision('SELL- No space') == 'SELL'
    assert extract_llm_decision('   buy -  Extra spaces   ') == 'BUY'
    # New format: "75% BUY - explanation"
    assert extract_llm_decision('75% BUY - Strong momentum') == 'BUY'
    assert extract_llm_decision('30% SELL - Bearish trend') == 'SELL'
    assert extract_llm_decision('50% HOLD - Mixed signals') == 'HOLD'
    # Edge cases
    assert extract_llm_decision(None) is None
    assert extract_llm_decision('') == 'EMPTY_DECISION'
    assert extract_llm_decision('neutral - Sideways') == 'EMPTY_DECISION'


# Test: extract_llm_confidence
def test_extract_llm_confidence():
    assert extract_llm_confidence('75% BUY - Strong momentum') == 0.75
    assert extract_llm_confidence('30% SELL - Bearish trend') == 0.30
    assert extract_llm_confidence('100% BUY - All signals aligned') == 1.0
    assert extract_llm_confidence('0% HOLD - No conviction') == 0.0
    # Old format without confidence → default 0.5
    assert extract_llm_confidence('BUY - Strong momentum') == 0.5
    assert extract_llm_confidence(None) == 0.5
    assert extract_llm_confidence('') == 0.5


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




# Test: generate_action_column (DEFAULT = consensus LLM + technical)
def test_generate_action_column_default():
    df_test = pd.DataFrame({
        'symbol': ['AAPL', 'MSFT', 'GOOGL', 'AMZN'],
        'llm_opinion': [
            'BUY - Strong momentum.',           # BUY, technical SELL → HOLD (disagreement)
            'BUY - All indicators up.',          # BUY, technical BUY → BUY (consensus)
            'SELL - Bearish trend.',              # SELL, technical BUY → HOLD (disagreement)
            'SELL - Weak momentum.',              # SELL, technical SELL → SELL (consensus)
        ],
        'manual_financial_analysis': [
            '0.40 SELL',
            '0.60 BUY',
            '0.55 BUY',
            '0.70 SELL',
        ],
    })
    df_result = generate_action_column(df_test.copy(), "DEFAULT")

    expected = ['HOLD', 'BUY', 'HOLD', 'SELL']
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


# Test: apply_technical_filter (consensus logic with confidence weighting)
def test_apply_technical_filter():
    # === CONSENSUS: BUY only when both agree ===
    # LLM BUY(0.5) + technical BUY(0.6) → BUY (both agree)
    assert apply_technical_filter('BUY', '0.60 BUY') == 'BUY'
    # LLM BUY(0.5) + technical SELL(0.35) → HOLD (disagreement)
    assert apply_technical_filter('BUY', '0.35 SELL') == 'HOLD'
    # LLM BUY(0.5) + technical HOLD(0.50) → HOLD (not enough consensus)
    assert apply_technical_filter('BUY', '0.50 HOLD') == 'HOLD'

    # === CONSENSUS: SELL only when both agree ===
    # LLM SELL(0.5) + technical SELL(0.8) → SELL (both agree)
    assert apply_technical_filter('SELL', '0.80 SELL') == 'SELL'
    # LLM SELL(0.5) + technical BUY(0.55) → HOLD (disagreement)
    assert apply_technical_filter('SELL', '0.55 BUY') == 'HOLD'

    # === LLM confidence matters ===
    # High-conf LLM BUY(0.9) + low-conf technical HOLD(0.1) → BUY (LLM dominates)
    assert apply_technical_filter('BUY', '0.10 HOLD', llm_confidence=0.9) == 'BUY'
    # Low-conf LLM BUY(0.2) + high-conf technical SELL(0.8) → SELL (technical dominates)
    assert apply_technical_filter('BUY', '0.80 SELL', llm_confidence=0.2) == 'SELL'
    # Equal conf, disagreement → HOLD
    assert apply_technical_filter('BUY', '0.50 SELL', llm_confidence=0.5) == 'HOLD'

    # === HOLD from LLM, strong technical can promote ===
    # LLM HOLD(0.3) + technical BUY(0.8) → BUY (technical strong enough)
    assert apply_technical_filter('HOLD', '0.80 BUY', llm_confidence=0.3) == 'BUY'
    # LLM HOLD(0.3) + technical SELL(0.8) → SELL (technical strong enough)
    assert apply_technical_filter('HOLD', '0.80 SELL', llm_confidence=0.3) == 'SELL'

    # === Error/fallback cases ===
    assert apply_technical_filter(None, '0.50 BUY') == 'BUY'
    assert apply_technical_filter(None, '0.30 BUY') is None
    assert apply_technical_filter('BUY', None) == 'BUY'


# Test: generate_action_column with force_opinion = LLM1 (GPT only, no consensus)
def test_generate_action_column_force_llm():
    df_test = pd.DataFrame(test_data)
    df_result = generate_action_column(df_test.copy(), opinion_type="LLM1")

    # LLM1 = GPT only, ignores technical analysis
    expected = ['SELL', 'BUY', 'EMPTY_DECISION', 'SELL', 'EMPTY_DECISION']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[LLM1] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"


# Test: generate_action_column DEFAULT with weighted consensus (1.2x tech, threshold 0.5)
def test_generate_action_column_default_consensus():
    df_test = pd.DataFrame({
        'symbol': [
            'CLEAR_BUY',       # Both agree BUY → BUY
            'CLEAR_SELL',      # Both agree SELL → SELL
            'STRONG_HOLD',     # LLM HOLD 70% blocks weak tech BUY 0.50 → HOLD
            'BORDERLINE_BUY',  # LLM HOLD 50% + decent tech BUY 0.65 → BUY (tech strong enough)
            'HOLD_OVERRIDES',  # LLM BUY + strong tech HOLD 0.70 → HOLD (tech weight blocks)
            'WEAK_HOLD_PASS',  # LLM BUY + very weak tech HOLD 0.30 → BUY (weak HOLD can't block)
            'DISAGREEMENT',    # LLM SELL + tech BUY → HOLD (conflict)
            'NO_TECH',         # LLM BUY + no technical → BUY (fallback)
            'LLM_ERROR',       # LLM error + tech BUY 0.60 → BUY (fallback)
            'STRONG_TECH_BUY', # LLM HOLD 70% + strong tech BUY 0.65 → BUY (tech passes scrutiny)
        ],
        'llm_opinion': [
            '80% BUY - All indicators align.',           # clear BUY
            '75% SELL - Breakdown confirmed.',            # clear SELL
            '70% HOLD - RSI divergence risk.',            # skeptical LLM blocks weak tech
            '50% HOLD - Minor concerns.',                 # mild LLM skepticism
            'BUY - Looks good.',                          # LLM says BUY but tech disagrees
            'BUY - Momentum up.',                         # LLM BUY vs very weak tech HOLD
            '60% SELL - Bearish divergence.',              # LLM SELL vs tech BUY
            'BUY - Uptrend.',                             # no tech data
            'error: API timeout',                         # LLM failed
            '70% HOLD - Overbought near resistance.',     # skeptical but tech is strong
        ],
        'manual_financial_analysis': [
            '0.70 BUY',    # both agree → BUY
            '0.60 SELL',   # both agree → SELL
            '0.50 BUY',    # weak tech BUY blocked by strong LLM HOLD
            '0.65 BUY',    # decent tech BUY passes mild LLM skepticism
            '0.70 HOLD',   # strong tech HOLD blocks LLM BUY
            '0.30 HOLD',   # very weak tech HOLD overridden by LLM BUY
            '0.60 BUY',    # tech BUY but LLM SELL → conflict
            None,           # no tech → fallback to LLM
            '0.60 BUY',    # LLM error → fallback to tech
            '0.65 BUY',    # strong tech survives LLM scrutiny
        ],
    })
    df_result = generate_action_column(df_test.copy(), opinion_type="DEFAULT")

    # Expected results with weighted consensus (1.2x tech, threshold ≥0.5)
    expected = {
        'CLEAR_BUY': 'BUY',         # both agree, easy
        'CLEAR_SELL': 'SELL',        # both agree, easy
        'STRONG_HOLD': 'HOLD',      # LLM HOLD 70% blocks weak tech BUY 0.50 (norm=0.46)
        'BORDERLINE_BUY': 'BUY',    # mild HOLD + decent tech → passes (norm=0.61)
        'HOLD_OVERRIDES': 'HOLD',   # strong tech HOLD outweighs LLM BUY (norm=0.37)
        'WEAK_HOLD_PASS': 'BUY',    # very weak HOLD can't block LLM BUY (norm=0.58)
        'DISAGREEMENT': 'HOLD',     # SELL vs BUY → conflict (norm=0.09)
        'NO_TECH': 'BUY',           # fallback to LLM
        'LLM_ERROR': 'BUY',         # fallback to tech (conf 0.60 ≥ 0.5)
        'STRONG_TECH_BUY': 'BUY',   # tech survives LLM scrutiny (norm=0.53)
    }
    for i, symbol in enumerate(df_test['symbol']):
        exp = expected[symbol]
        got = df_result.loc[i, 'action']
        assert got == exp, f"[DEFAULT consensus] {symbol}: expected {exp}, got {got}"

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
