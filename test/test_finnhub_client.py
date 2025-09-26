# test_finnhub_client.py
import os
import pytest
from tools.finnhub_client import analyze_market_losers_from_interest_list, SYMBOLS_INTEREST_LIST
from dotenv import load_dotenv

# Load .env file only if not running in production (e.g., GitHub Actions)
if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

# Ensure API key is available
def check_api_key():
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        pytest.fail("❌ FINNHUB_API_KEY not set in environment")

def test_returns_list():
    losers = analyze_market_losers_from_interest_list(SYMBOLS_INTEREST_LIST, top_n=1)
    assert isinstance(losers, list), "Function should return a list"

def test_items_are_dicts():
    losers = analyze_market_losers_from_interest_list(SYMBOLS_INTEREST_LIST, top_n=1)
    for item in losers:
        assert isinstance(item, dict), "Each item should be a dictionary"

def test_required_keys_exist():
    losers = analyze_market_losers_from_interest_list(SYMBOLS_INTEREST_LIST, top_n=1)
    for item in losers:
        assert "symbol" in item
        assert "current_price" in item
        assert "change_percent" in item

def test_change_percent_is_negative():
    losers = analyze_market_losers_from_interest_list(SYMBOLS_INTEREST_LIST, top_n=1)
    for item in losers:
        assert item["change_percent"] < 0, f"{item['symbol']} is not a loser"

def test_limit_applied():
    top_n = 1
    losers = analyze_market_losers_from_interest_list(SYMBOLS_INTEREST_LIST, top_n=top_n)
    assert len(losers) <= top_n, f"Should return no more than {top_n} items"
