# test_finnhub_client.py
import os
import pytest
import requests
from unittest.mock import patch, MagicMock
from tools.finnhub_client import get_symbols_info, get_quote


MOCK_QUOTE_RESPONSES = {
    "AAPL": {"c": 150.0, "dp": -2.5},
    "MSFT": {"c": 300.0, "dp": -1.2},
    "GOOGL": {"c": 2800.0, "dp": 0.5},
    "TSLA": {"c": 200.0, "dp": -3.8},
}


@patch("tools.finnhub_client.get_quote")
def test_get_symbols_info_with_mock(mock_get_quote):
    """Test get_symbols_info with mocked Finnhub API calls."""
    def quote_side_effect(symbol):
        return MOCK_QUOTE_RESPONSES.get(symbol, {"c": 0, "dp": 0})

    mock_get_quote.side_effect = quote_side_effect

    result = get_symbols_info(["AAPL", "MSFT"])
    assert len(result) == 2
    assert result[0]["symbol"] == "AAPL"
    assert result[0]["current_price"] == 150.0
    assert result[0]["change_percent"] == -2.5
    assert mock_get_quote.call_count == 2


@patch("tools.finnhub_client.get_quote")
def test_get_symbols_info_skips_failed_symbols(mock_get_quote):
    """Symbols that return None from get_quote should be skipped, not crash."""
    def quote_side_effect(symbol):
        if symbol == "BHE.DE":
            return None  # Unknown symbol
        return MOCK_QUOTE_RESPONSES.get(symbol, None)

    mock_get_quote.side_effect = quote_side_effect

    result = get_symbols_info(["AAPL", "BHE.DE", "MSFT"])
    assert len(result) == 2  # BHE.DE skipped
    symbols = [r["symbol"] for r in result]
    assert "BHE.DE" not in symbols
    assert "AAPL" in symbols
    assert "MSFT" in symbols


@patch("tools.finnhub_client.get_quote")
def test_get_symbols_info_skips_zero_price(mock_get_quote):
    """Symbols with price 0 (Finnhub unknown symbol response) should be skipped."""
    def quote_side_effect(symbol):
        if symbol == "FAKE":
            return {"c": 0, "dp": 0}  # Finnhub returns zeros for unknown symbols
        return MOCK_QUOTE_RESPONSES.get(symbol, None)

    mock_get_quote.side_effect = quote_side_effect

    result = get_symbols_info(["AAPL", "FAKE"])
    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"


@patch("tools.finnhub_client.requests.get")
def test_get_quote_handles_timeout(mock_get):
    """get_quote should return None on timeout, not crash."""
    mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

    result = get_quote("AAPL")
    assert result is None


@patch("tools.finnhub_client.requests.get")
def test_get_quote_handles_http_error(mock_get):
    """get_quote should return None on HTTP 404/500, not crash."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
    mock_get.return_value = mock_response

    result = get_quote("BHE.DE")
    assert result is None


@patch("tools.finnhub_client.requests.get")
def test_get_quote_handles_unknown_symbol(mock_get):
    """Finnhub returns all zeros for unknown symbols — should return None."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"c": 0, "d": None, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0}
    mock_get.return_value = mock_response

    result = get_quote("BHE.DE")
    assert result is None


@patch.dict(os.environ, {"FINNHUB_API_KEY": "k123"})
@patch("tools.finnhub_client.API_KEY", None)
@patch("tools.finnhub_client.requests.get")
def test_get_quote_sends_key_in_header_not_url(mock_get):
    mock_get.return_value.json.return_value = {"c": 10.0, "dp": 1.0}
    get_quote("AAPL")
    _, kwargs = mock_get.call_args
    assert "token" not in kwargs["params"]
    assert kwargs["headers"]["X-Finnhub-Token"] == "k123"
