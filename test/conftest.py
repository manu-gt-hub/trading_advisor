import pytest
from unittest.mock import patch

from tools import custom_financial_calc


@pytest.fixture(autouse=True)
def _no_market_network():
    """Keep the suite offline and fast: valuation and S&P500 context hit yfinance.
    Tests that need specific values still override these with their own @patch."""
    with patch.object(custom_financial_calc, "_get_valuation_metrics",
                      return_value=dict(custom_financial_calc.NEUTRAL_VALUATION)), \
         patch.object(custom_financial_calc, "_get_sp500_trend", return_value=(None, 0.0)):
        yield
