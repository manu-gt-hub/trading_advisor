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
    """Fetch current quote data for a symbol from Finnhub.
    Returns the JSON response dict, or None if the request fails or the symbol is not found.
    """
    url = "https://finnhub.io/api/v1/quote"
    params = {"symbol": symbol, "token": API_KEY}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Finnhub returns all zeros for unknown symbols (c=0, dp=0, etc.)
        if not data or data.get("c") is None or data.get("c") == 0:
            logger.warning(f"⚠️ Finnhub returned no valid data for {symbol}: {data}")
            return None

        return data
    except requests.exceptions.Timeout:
        logger.error(f"⏱️ Timeout fetching quote for {symbol}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"❌ HTTP error for {symbol}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Request failed for {symbol}: {e}")
        return None
    except (ValueError, KeyError) as e:
        logger.error(f"❌ Invalid response for {symbol}: {e}")
        return None

def get_symbols_info(symbols):
    symbols_info_list = []

    logger.info(f"Gathering market symbols info...")

    for symbol in symbols:
        try:
            quote = get_quote(symbol)

            if quote is None:
                logger.warning(f"⚠️ Skipping {symbol}: no valid quote data from Finnhub")
                continue

            current_price = quote.get("c")
            change_percent = quote.get("dp")

            if current_price is None or current_price <= 0:
                logger.warning(f"⚠️ Skipping {symbol}: invalid price {current_price}")
                continue

            symbols_info_list.append({
                "symbol": symbol,
                "current_price": current_price,
                "change_percent": change_percent
            })
        except Exception as e:
            logger.error(f"❌ Unexpected error for {symbol}: {e}. Skipping.")

    logger.info(f"✅ Got valid data for {len(symbols_info_list)}/{len(symbols)} symbols")
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
    
    logger.info(f"✅  successfully got market losers")

    if top_n is None:
        return losers  # return full list
    else:
        return losers[:top_n]

