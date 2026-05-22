import sys
import os
import pandas as pd
import pytest
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def filter_buys_by_confidence(analysis_df, min_confidence):
    """Replicates the filtering logic from main.py for testability."""
    buy_df = analysis_df[
        (analysis_df['action'] == 'BUY') &
        (analysis_df['technical_confidence'] >= min_confidence)
    ].copy()
    return buy_df


def filter_buys_by_risk_reward(buy_df, min_rr=1.5):
    """Replicates the R:R filtering logic from main.py for testability."""
    if buy_df.empty or 'risk_reward_ratio' not in buy_df.columns:
        return buy_df
    bad_rr = buy_df[buy_df['risk_reward_ratio'].apply(
        lambda x: pd.notna(x) and x < min_rr
    )]
    return buy_df[~buy_df.index.isin(bad_rr.index)].copy()


class TestMinBuyConfidenceFilter:

    def _build_analysis_df(self):
        return pd.DataFrame({
            'symbol': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'],
            'current_price': [150.0, 300.0, 2800.0, 3400.0, 700.0],
            'action': ['BUY', 'BUY', 'BUY', 'SELL', 'HOLD'],
            'technical_confidence': [0.65, 0.30, 0.10, 0.80, 0.50],
        })

    def test_default_threshold_filters_low_confidence(self):
        df = self._build_analysis_df()
        result = filter_buys_by_confidence(df, min_confidence=0.5)

        # Only AAPL (0.65) passes; MSFT (0.30) and GOOGL (0.10) are filtered out
        assert list(result['symbol']) == ['AAPL']

    def test_low_threshold_allows_more_buys(self):
        df = self._build_analysis_df()
        result = filter_buys_by_confidence(df, min_confidence=0.1)

        # AAPL (0.65), MSFT (0.30), GOOGL (0.10) all pass
        assert list(result['symbol']) == ['AAPL', 'MSFT', 'GOOGL']

    def test_high_threshold_filters_all_buys(self):
        df = self._build_analysis_df()
        result = filter_buys_by_confidence(df, min_confidence=0.9)

        # No BUY has confidence >= 0.9
        assert result.empty

    def test_non_buy_actions_are_never_included(self):
        df = self._build_analysis_df()
        result = filter_buys_by_confidence(df, min_confidence=0.0)

        # Even with threshold 0, SELL and HOLD are excluded
        assert 'AMZN' not in result['symbol'].values
        assert 'TSLA' not in result['symbol'].values

    def test_exact_threshold_boundary(self):
        df = self._build_analysis_df()
        # MSFT has exactly 0.30 confidence
        result = filter_buys_by_confidence(df, min_confidence=0.30)
        assert 'MSFT' in result['symbol'].values

        result = filter_buys_by_confidence(df, min_confidence=0.31)
        assert 'MSFT' not in result['symbol'].values


class TestRiskRewardFilter:

    def _build_buy_df(self):
        return pd.DataFrame({
            'symbol': ['AAPL', 'MSFT', 'GOOGL', 'NVDA'],
            'action': ['BUY', 'BUY', 'BUY', 'BUY'],
            'risk_reward_ratio': [2.5, 1.0, 1.5, None],
        })

    def test_blocks_low_rr(self):
        df = self._build_buy_df()
        result = filter_buys_by_risk_reward(df)
        # MSFT (1.0 < 1.5) blocked
        assert 'MSFT' not in result['symbol'].values

    def test_keeps_good_rr(self):
        df = self._build_buy_df()
        result = filter_buys_by_risk_reward(df)
        # AAPL (2.5) and GOOGL (1.5) pass
        assert 'AAPL' in result['symbol'].values
        assert 'GOOGL' in result['symbol'].values

    def test_keeps_nan_rr(self):
        df = self._build_buy_df()
        result = filter_buys_by_risk_reward(df)
        # NVDA (None) passes — don't block when data is missing
        assert 'NVDA' in result['symbol'].values

    def test_exact_boundary(self):
        df = self._build_buy_df()
        result = filter_buys_by_risk_reward(df, min_rr=1.5)
        # GOOGL has exactly 1.5 — should pass
        assert 'GOOGL' in result['symbol'].values

    def test_empty_df(self):
        df = pd.DataFrame(columns=['symbol', 'action', 'risk_reward_ratio'])
        result = filter_buys_by_risk_reward(df)
        assert result.empty


def _is_market_day(today):
    """Testable version of market day check — receives date as parameter."""
    if today.weekday() >= 5:
        return False
    us_holidays = [(1, 1), (7, 4), (12, 25)]
    if (today.month, today.day) in us_holidays:
        return False
    return True


class TestMarketDayGuard:

    def test_weekday_is_market_day(self):
        assert _is_market_day(date(2025, 5, 19)) is True  # Monday

    def test_saturday_is_not_market_day(self):
        assert _is_market_day(date(2025, 5, 17)) is False  # Saturday

    def test_sunday_is_not_market_day(self):
        assert _is_market_day(date(2025, 5, 18)) is False  # Sunday

    def test_christmas_is_not_market_day(self):
        assert _is_market_day(date(2025, 12, 25)) is False  # Thursday

    def test_new_years_is_not_market_day(self):
        assert _is_market_day(date(2025, 1, 1)) is False  # Wednesday

    def test_independence_day_is_not_market_day(self):
        assert _is_market_day(date(2025, 7, 4)) is False  # Friday

    def test_regular_friday_is_market_day(self):
        assert _is_market_day(date(2025, 5, 23)) is True  # Friday
