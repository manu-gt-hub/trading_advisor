import os
import requests
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load .env file only if not running in production (e.g., GitHub Actions)
if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

API_KEY = os.environ.get("FINNHUB_API_KEY")


def auth_headers():
    """Finnhub auth via header so the key never appears in URLs, logs or exceptions."""
    return {"X-Finnhub-Token": API_KEY or os.environ.get("FINNHUB_API_KEY", "")}

def get_quote(symbol):
    """Fetch current quote data for a symbol from Finnhub.
    Returns the JSON response dict, or None if the request fails or the symbol is not found.
    """
    url = "https://finnhub.io/api/v1/quote"
    params = {"symbol": symbol}
    try:
        response = requests.get(url, params=params, headers=auth_headers(), timeout=10)
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
