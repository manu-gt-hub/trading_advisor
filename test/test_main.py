import sys
import os
import pandas as pd
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def filter_buys_by_confidence(analysis_df, min_confidence):
    """Replicates the filtering logic from main.py for testability."""
    buy_df = analysis_df[
        (analysis_df['action'] == 'BUY') &
        (analysis_df['technical_confidence'] >= min_confidence)
    ].copy()
    return buy_df


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
