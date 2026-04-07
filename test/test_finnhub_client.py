# test_finnhub_client.py
import os
import pytest
from unittest.mock import patch, MagicMock
from tools.finnhub_client import analyze_market_losers_from_interest_list, get_symbols_info, get_quote


# Mock data matching Finnhub API response format
MOCK_SYMBOLS = [
    {"symbol": "AAPL", "current_price": 150.0, "change_percent": -2.5},
    {"symbol": "MSFT", "current_price": 300.0, "change_percent": -1.2},
    {"symbol": "GOOGL", "current_price": 2800.0, "change_percent": 0.5},
    {"symbol": "TSLA", "current_price": 200.0, "change_percent": -3.8},
]

MOCK_QUOTE_RESPONSES = {
    "AAPL": {"c": 150.0, "dp": -2.5},
    "MSFT": {"c": 300.0, "dp": -1.2},
    "GOOGL": {"c": 2800.0, "dp": 0.5},
    "TSLA": {"c": 200.0, "dp": -3.8},
}


def test_returns_list():
    losers = analyze_market_losers_from_interest_list(MOCK_SYMBOLS, top_n=1)
    assert isinstance(losers, list), "Function should return a list"

def test_items_are_dicts():
    losers = analyze_market_losers_from_interest_list(MOCK_SYMBOLS, top_n=1)
    for item in losers:
        assert isinstance(item, dict), "Each item should be a dictionary"

def test_required_keys_exist():
    losers = analyze_market_losers_from_interest_list(MOCK_SYMBOLS, top_n=1)
    for item in losers:
        assert "symbol" in item
        assert "current_price" in item
        assert "change_percent" in item

def test_change_percent_is_negative():
    losers = analyze_market_losers_from_interest_list(MOCK_SYMBOLS, top_n=2)
    for item in losers:
        assert item["change_percent"] < 0, f"{item['symbol']} is not a loser"

def test_limit_applied():
    top_n = 1
    losers = analyze_market_losers_from_interest_list(MOCK_SYMBOLS, top_n=top_n)
    assert len(losers) <= top_n, f"Should return no more than {top_n} items"

def test_sorted_by_most_negative():
    losers = analyze_market_losers_from_interest_list(MOCK_SYMBOLS)
    # TSLA (-3.8) should be first, then AAPL (-2.5), then MSFT (-1.2)
    assert losers[0]["symbol"] == "TSLA"
    assert losers[1]["symbol"] == "AAPL"

def test_positive_change_excluded():
    losers = analyze_market_losers_from_interest_list(MOCK_SYMBOLS)
    symbols = [l["symbol"] for l in losers]
    assert "GOOGL" not in symbols, "Positive change symbols should be excluded"


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
