import os
import requests
from dotenv import load_dotenv
import ast
import logging

logger = logging.getLogger(__name__)

# Load .env file only if not running in production (e.g., GitHub Actions)
if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

# Your predefined symbols of interest
SYMBOLS_INTEREST_LIST = ast.literal_eval(os.environ.get("SYMBOLS_INTEREST_LIST", "[]"))

API_KEY = os.environ.get("FINNHUB_API_KEY")

def get_quote(symbol):
    """Fetch current quote data for a symbol from Finnhub"""
    url = "https://finnhub.io/api/v1/quote"
    params = {"symbol": symbol, "token": API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def get_symbols_info(symbols):
    symbols_info_list = []

    logger.info(f"Gathering market symbols info...")

    for symbol in symbols:
        try:
            quote = get_quote(symbol)
            current_price = quote.get("c")
            change_percent = quote.get("dp")

            symbols_info_list.append({
                "symbol": symbol,
                "current_price": current_price,
                "change_percent": change_percent
            })
        except Exception as e:
            logger.error(f"❌ Error retrieving data for {symbol}: {e}")

    # Sort the list by most negative change
    return symbols_info_list

def analyze_market_losers_from_interest_list(symbols, top_n=None):
    """
    Analyze a list of predefined symbols and return the top losers
    based on percentage drop (dp field).
    """
    losers = []

    logger.info(f"Analyzing market losers...")

    for symbol in symbols:
        try:
            current_price = symbol['current_price']
            change_percent = symbol['change_percent']

            # if symbol has had a change percent we add it as loser
            if change_percent is not None and change_percent < 0:
                losers.append(symbol)
        except Exception as e:
            logger.error(f"❌ Error retrieving data for {symbol}: {e}")

    # Sort the list by most negative change
    losers.sort(key=lambda x: x["change_percent"])
    
    logger.info(f"✅  succesfully got market losers")

    if top_n is None:
        return losers  # return full list
    else:
        return losers[:top_n]

