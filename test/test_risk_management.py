import sys
import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from risk_management import compute_stop_loss_take_profit, compute_position_size, filter_correlated_buys


class TestStopLossTakeProfit:

    def test_basic_atr_based(self):
        result = compute_stop_loss_take_profit(100.0, 5.0)
        assert result["stop_loss"] == 90.0   # 100 - 2*5
        assert result["take_profit"] == 115.0  # 100 + 3*5
        assert result["risk_reward_ratio"] == 1.5  # 15/10

    def test_with_revenue_percentage(self):
        result = compute_stop_loss_take_profit(100.0, 5.0, revenue_percentage=20)
        assert result["stop_loss"] == 90.0
        assert result["take_profit"] == 120.0  # 100 * 1.20
        assert result["risk_reward_ratio"] == 2.0  # 20/10

    def test_invalid_atr(self):
        result = compute_stop_loss_take_profit(100.0, 0)
        assert result["stop_loss"] is None
        assert result["take_profit"] is None

    def test_nan_atr(self):
        result = compute_stop_loss_take_profit(100.0, float('nan'))
        assert result["stop_loss"] is None

    def test_stop_loss_floor(self):
        # Very high ATR relative to price — stop loss should not go below 0.01
        result = compute_stop_loss_take_profit(5.0, 10.0)
        assert result["stop_loss"] == 0.01


class TestPositionSize:

    def test_basic_sizing(self):
        result = compute_position_size(
            portfolio_value=10000, risk_per_trade_pct=2.0,
            current_price=100.0, stop_loss=95.0
        )
        # risk_amount = 200, risk_per_share = 5, uncapped shares = 40
        # position_value = 4000 > 20% cap (2000), so capped to 2000/100 = 20
        assert result["shares"] == 20
        assert result["position_value"] == 2000.0
        assert result["risk_amount"] == 200.0

    def test_cap_at_20_percent(self):
        # Large position that exceeds 20% cap
        result = compute_position_size(
            portfolio_value=10000, risk_per_trade_pct=10.0,
            current_price=50.0, stop_loss=49.0
        )
        # risk_amount = 1000, risk_per_share = 1, shares = 1000 → capped at 20% = 2000/50 = 40
        assert result["shares"] == 40
        assert result["position_value"] == 2000.0

    def test_zero_risk_per_share(self):
        result = compute_position_size(
            portfolio_value=10000, risk_per_trade_pct=2.0,
            current_price=100.0, stop_loss=100.0
        )
        assert result["shares"] == 0

    def test_invalid_inputs(self):
        result = compute_position_size(0, 2.0, 100.0, 95.0)
        assert result["shares"] == 0


class TestCorrelationFilter:

    def test_single_buy_passthrough(self):
        df = pd.DataFrame({"symbol": ["AAPL"], "technical_confidence": [0.7]})
        result = filter_correlated_buys(df)
        assert len(result) == 1

    def test_empty_df(self):
        df = pd.DataFrame(columns=["symbol", "technical_confidence"])
        result = filter_correlated_buys(df)
        assert len(result) == 0

    @patch("risk_management.yf.Ticker")
    def test_correlated_pair_filters_lower_confidence(self, mock_ticker):
        # Create fake price data where AAPL and MSFT are perfectly correlated
        import numpy as np
        dates = pd.date_range("2024-01-01", periods=100)
        prices = np.cumsum(np.random.randn(100)) + 100

        mock_hist_aapl = pd.DataFrame({"Close": prices}, index=dates)
        mock_hist_msft = pd.DataFrame({"Close": prices * 1.1}, index=dates)  # same direction = corr ~1.0

        def ticker_side_effect(sym):
            mock = MagicMock()
            if sym == "AAPL":
                mock.history.return_value = mock_hist_aapl
            else:
                mock.history.return_value = mock_hist_msft
            return mock

        mock_ticker.side_effect = ticker_side_effect

        df = pd.DataFrame({
            "symbol": ["AAPL", "MSFT"],
            "technical_confidence": [0.8, 0.5]
        })
        result = filter_correlated_buys(df, max_correlation=0.75)
        # MSFT should be removed (lower confidence, high correlation)
        assert len(result) == 1
        assert result.iloc[0]["symbol"] == "AAPL"

    @patch("risk_management.yf.Ticker")
    def test_uncorrelated_pair_keeps_both(self, mock_ticker):
        import numpy as np
        dates = pd.date_range("2024-01-01", periods=100)

        mock_hist_aapl = pd.DataFrame({"Close": np.cumsum(np.random.randn(100)) + 100}, index=dates)
        mock_hist_msft = pd.DataFrame({"Close": np.cumsum(np.random.randn(100)) + 200}, index=dates)

        def ticker_side_effect(sym):
            mock = MagicMock()
            if sym == "AAPL":
                mock.history.return_value = mock_hist_aapl
            else:
                mock.history.return_value = mock_hist_msft
            return mock

        mock_ticker.side_effect = ticker_side_effect

        df = pd.DataFrame({
            "symbol": ["AAPL", "MSFT"],
            "technical_confidence": [0.8, 0.7]
        })
        result = filter_correlated_buys(df, max_correlation=0.99)
        # With random independent data and very high threshold, both should stay
        assert len(result) == 2
