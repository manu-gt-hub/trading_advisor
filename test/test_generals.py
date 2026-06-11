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
    apply_audit_veto,
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




# Test: generate_action_column (DEFAULT = technical decides, LLM only audits BUY)
def test_generate_action_column_default():
    df_test = pd.DataFrame({
        'symbol': ['AAPL', 'MSFT', 'GOOGL', 'AMZN'],
        'llm_opinion': [
            'COHERENT | adj=+0.05 | aligned',      # technical BUY, audit OK → BUY
            'INCOHERENT | adj=-0.30 | divergence', # technical BUY, audit veto → HOLD
            'SELL - LLM not called (technical decides)',  # technical SELL → SELL
            'HOLD - LLM not called (technical decides)',  # technical HOLD → HOLD
        ],
        'manual_financial_analysis': [
            '0.60 BUY | regime=TRENDING_UP',
            '0.55 BUY | regime=TRENDING_UP',
            '-0.40 SELL | regime=TRENDING_DOWN',
            '0.10 HOLD | regime=RANGE',
        ],
    })
    df_result = generate_action_column(df_test.copy(), "DEFAULT")

    # Technical engine decides; LLM audit only downgrades a BUY to HOLD on INCOHERENT
    expected = ['BUY', 'HOLD', 'SELL', 'HOLD']
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


# Test: apply_audit_veto (LLM may ONLY downgrade a technical BUY to HOLD on INCOHERENT)
def test_apply_audit_veto():
    # Technical BUY + INCOHERENT audit → HOLD (veto)
    assert apply_audit_veto('BUY', 'INCOHERENT | adj=-0.30 | bearish divergence') == 'HOLD'
    # Technical BUY + COHERENT audit → BUY (no veto)
    assert apply_audit_veto('BUY', 'COHERENT | adj=+0.05 | aligned') == 'BUY'

    # Veto applies ONLY to BUY — never flips SELL or HOLD
    assert apply_audit_veto('SELL', 'INCOHERENT | adj=-0.30 | whatever') == 'SELL'
    assert apply_audit_veto('HOLD', 'INCOHERENT | adj=-0.30 | whatever') == 'HOLD'

    # LLM can never create or upgrade a signal — non-BUY stays as technical decided
    assert apply_audit_veto('HOLD', 'COHERENT | adj=+0.10 | strong') == 'HOLD'

    # Missing/empty audit → keep technical decision
    assert apply_audit_veto('BUY', None) == 'BUY'
    assert apply_audit_veto('BUY', '') == 'BUY'


# Test: generate_action_column with force_opinion = LLM1 (GPT only, no consensus)
def test_generate_action_column_force_llm():
    df_test = pd.DataFrame(test_data)
    df_result = generate_action_column(df_test.copy(), opinion_type="LLM1")

    # LLM1 = GPT only, ignores technical analysis
    expected = ['SELL', 'BUY', 'EMPTY_DECISION', 'SELL', 'EMPTY_DECISION']
    for i, exp in enumerate(expected):
        assert df_result.loc[i, 'action'] == exp, f"[LLM1] Index {i}: expected {exp}, got {df_result.loc[i, 'action']}"


# Test: DEFAULT — technical engine is the sole decider; the LLM cannot create a BUY
def test_generate_action_column_default_technical_decides():
    df_test = pd.DataFrame({
        'symbol': [
            'TECH_BUY_OK',        # technical BUY, audit COHERENT → BUY
            'TECH_BUY_VETOED',    # technical BUY, audit INCOHERENT → HOLD
            'TECH_SELL',          # technical SELL (no LLM) → SELL
            'TECH_HOLD',          # technical HOLD (no LLM) → HOLD
            'LLM_CANNOT_CREATE',  # technical HOLD even if audit text mentions BUY → HOLD
        ],
        'llm_opinion': [
            'COHERENT | adj=+0.08 | trend+momentum aligned',
            'INCOHERENT | adj=-0.30 | overbought exhaustion',
            'SELL - LLM not called (technical decides)',
            'HOLD - LLM not called (technical decides)',
            'COHERENT | adj=+0.10 | would be a great BUY',
        ],
        'manual_financial_analysis': [
            '0.62 BUY | regime=TRENDING_UP',
            '0.58 BUY | regime=TRENDING_UP',
            '-0.45 SELL | regime=TRENDING_DOWN',
            '0.05 HOLD | regime=RANGE',
            '0.05 HOLD | regime=RANGE',
        ],
    })
    df_result = generate_action_column(df_test.copy(), opinion_type="DEFAULT")

    expected = {
        'TECH_BUY_OK': 'BUY',
        'TECH_BUY_VETOED': 'HOLD',
        'TECH_SELL': 'SELL',
        'TECH_HOLD': 'HOLD',
        'LLM_CANNOT_CREATE': 'HOLD',
    }
    for i, symbol in enumerate(df_test['symbol']):
        exp = expected[symbol]
        got = df_result.loc[i, 'action']
        assert got == exp, f"[DEFAULT technical-decides] {symbol}: expected {exp}, got {got}"

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
