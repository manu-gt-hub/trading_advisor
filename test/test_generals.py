import pandas as pd
import numpy as np
import re
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
# Import all the necessary functions from your script
from general import (
    extract_custom_decision,
    apply_audit_veto,
    generate_action_column,
    add_urls_column,
    is_us_market_day,
    nyse_holidays,
    SecretRedactingFilter,
)

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


# Test: legacy LLM1/LLM2 modes fall back to DEFAULT (technical decides, audit veto applies)
def test_generate_action_column_legacy_llm_modes_fall_back_to_default():
    df_test = pd.DataFrame({
        'symbol': ['A', 'B', 'C'],
        'llm_opinion': [
            'COHERENT | adj=+0.05 | aligned',
            'INCOHERENT | adj=-0.30 | divergence',
            'HOLD - LLM not called (technical decides)',
        ],
        'manual_financial_analysis': [
            '0.60 BUY | regime=TRENDING_UP',
            '0.55 BUY | regime=TRENDING_UP',
            '0.10 HOLD | regime=RANGE',
        ],
    })
    for mode in ("LLM1", "LLM2"):
        df_result = generate_action_column(df_test.copy(), opinion_type=mode)
        assert list(df_result['action']) == ['BUY', 'HOLD', 'HOLD'], mode


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


def test_nyse_holidays_2026():
    from datetime import date
    assert nyse_holidays(2026) == {
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
        date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
        date(2026, 11, 26), date(2026, 12, 25),
    }


def test_new_year_on_saturday_is_not_observed_on_friday():
    from datetime import date
    # 2022-01-01 was a Saturday: NYSE stayed open on Friday 2021-12-31
    assert is_us_market_day(date(2021, 12, 31)) is True
    assert date(2021, 12, 31) not in nyse_holidays(2021)


def test_floating_holidays_are_closed():
    from datetime import date
    assert is_us_market_day(date(2025, 11, 27)) is False  # Thanksgiving
    assert is_us_market_day(date(2025, 4, 18)) is False   # Good Friday
    assert is_us_market_day(date(2025, 11, 28)) is True   # day after Thanksgiving (half day)


def test_secret_redacting_filter_masks_env_secrets(monkeypatch):
    import logging
    monkeypatch.setenv("FINNHUB_API_KEY", "supersecretkey123")
    record = logging.LogRecord("x", logging.ERROR, __file__, 1,
                               "HTTP error for url: https://finnhub.io/api/v1/quote?symbol=%s&token=supersecretkey123",
                               ("AAPL",), None)
    assert SecretRedactingFilter().filter(record) is True
    assert "supersecretkey123" not in record.getMessage()
    assert "AAPL" in record.getMessage()
