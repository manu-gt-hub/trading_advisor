# historicals.py

import os
import requests
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import yfinance as yf
from dotenv import load_dotenv

# Set up logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env file only if not running in production (e.g., GitHub Actions)
if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

# Environment-based constants
ALPHA_API_KEY = os.getenv('ALPHA_API_KEY')
ALPHA_URL = os.getenv("ALPHA_VANTAGE_URL")


def get_symbol_history_from_alpha(symbol: str, days: int):
    """
    Fetch historical daily stock data from Alpha Vantage for a given symbol.

    Parameters:
        symbol (str): Stock symbol (e.g., 'AAPL')
        days (int): Number of days to go back in history

    Returns:
        List of dictionaries with historical stock data or None on failure
    """
    params = {
        'function': 'TIME_SERIES_DAILY',
        'symbol': symbol,
        'apikey': ALPHA_API_KEY,
        'outputsize': 'full'
    }

    try:
        response = requests.get(ALPHA_URL, params=params, verify=False)
        response.raise_for_status()
        data = response.json()

        if 'Time Series (Daily)' not in data:
            logger.error(f"Alpha Vantage error for {symbol}: {data}")
            return None

        time_series = data['Time Series (Daily)']
        cutoff_date = datetime.now() - timedelta(days=days)

        # Filter the time series for records within the specified date range
        historical_data = [
            {
                'date': datetime.strptime(date, '%Y-%m-%d'),
                'open': values['1. open'],
                'high': values['2. high'],
                'low': values['3. low'],
                'close': values['4. close'],
                'volume': values['5. volume'],
            }
            for date, values in time_series.items()
            if datetime.strptime(date, '%Y-%m-%d') >= cutoff_date
        ]

        logger.info(f"Retrieved {len(historical_data)} records from Alpha Vantage for {symbol}")
        return historical_data

    except Exception as e:
        logger.error(f"Error fetching Alpha Vantage data for {symbol}: {e}")
        return None


def get_hist_data_from_yahoo(symbol: str, session: requests.Session, period: str = "5Y"):
    """
    Fetch historical stock data using Yahoo Finance via yfinance.

    Parameters:
        symbol (str): Stock symbol
        session (requests.Session): Reusable session object
        period (str): Period string for yfinance (e.g., '5Y')

    Returns:
        DataFrame with stock data or None if data is missing or failed
    """
    try:
        ticker = yf.Ticker(symbol, session=session)
        data = ticker.history(period=period)

        if data.empty:
            logger.warning(f"No Yahoo Finance data for {symbol}")
            return None

        logger.info(f"Retrieved {len(data)} records from Yahoo Finance for {symbol}")
        return data

    except Exception as e:
        logger.error(f"Yahoo Finance error for {symbol}: {e}")
        return None


def parse_data(data_dict):
    """
    Normalize and parse historical data from different sources into a standard DataFrame.

    Parameters:
        data_dict (dict): Dictionary with keys like "yahoo" or "alpha" and data values

    Returns:
        Parsed DataFrame or None if parsing fails
    """
    for source, data in data_dict.items():
        if data is None:
            logger.warning(f"No data from source: {source}")
            continue

        try:
            if source == "yahoo":
                # Parse and clean Yahoo Finance DataFrame
                df = pd.DataFrame(data).copy()
                df.columns = df.columns.str.replace(' ', '').str.lower()
                df = df.reset_index()
                df = df.rename(columns={'index': 'date'})

            elif source == "alpha":
                # Parse Alpha Vantage data from list of dicts
                df = pd.DataFrame(data).copy()
                df['date'] = pd.to_datetime(df['date'])
                df = df.astype({
                    'open': float, 'high': float, 'low': float,
                    'close': float, 'volume': int
                })

            logger.info(f"Parsed data successfully from source: {source}")
            return df

        except Exception as e:
            logger.error(f"Error parsing data from {source}: {e}")

    return None


def get_historical_data(symbol: str, force_source: str = None):
    """
    Entry point to fetch and parse historical stock data from available sources.

    Parameters:
        symbol (str): Stock symbol to query
        force_source (str, optional): 'yahoo' or 'alpha' to explicitly choose source

    Returns:
        Parsed DataFrame or None
    """
    logger.info(f"Fetching historical data for: {symbol}")
    session = requests.Session()
    session.verify = False  # Disabled certificate verification (for testing or insecure environments)
    data_dict = {}

    # Mapping available sources to functions
    sources = {
        "yahoo": lambda: get_hist_data_from_yahoo(symbol, session),
        "alpha": lambda: get_symbol_history_from_alpha(symbol, 1825)
    }

    # Use forced source if specified
    if force_source:
        logger.info(f"Forcing data source: {force_source}")
        data = sources.get(force_source, lambda: None)()
        if data:
            data_dict[force_source] = data
    else:
        # Try Yahoo first, fallback to Alpha
        data = sources["yahoo"]()
        if data:
            data_dict["yahoo"] = data
        else:
            data = sources["alpha"]()
            if data:
                data_dict["alpha"] = data

    # Parse and return result if any data was fetched
    return parse_data(data_dict) if data_dict else None


def create_hist_data():
    """
    Create mock historical stock data for testing or development purposes.

    Returns:
        DataFrame with 20 rows of synthetic stock data
    """
    start_date = datetime(2020, 5, 22)
    dates = [start_date + timedelta(days=i) for i in range(20)]

    # Set seed for reproducibility
    np.random.seed(42)
    
    # Simulate price and volume data
    open_prices = np.random.uniform(4.5, 5.0, 20)
    high_prices = open_prices + np.random.uniform(0.01, 0.05, 20)
    low_prices = open_prices - np.random.uniform(0.01, 0.05, 20)
    close_prices = open_prices + np.random.uniform(-0.02, 0.02, 20)
    volumes = np.random.randint(1000, 5000, 20)

    # Build DataFrame with simulated data
    df = pd.DataFrame({
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volumes,
        'dividends': 0.0,
        'stocksplits': 0.0,
        'date': pd.to_datetime(dates).tz_localize('America/New_York')
    })

    return df
