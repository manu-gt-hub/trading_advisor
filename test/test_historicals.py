# test/test_historicals.py

import sys
import os
import pytest
import warnings
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from historicals import get_historical_data, create_hist_data, parse_data

symbol = "MSFT"


def _mock_yahoo_dataframe():
    """Create a realistic mock Yahoo Finance DataFrame."""
    dates = pd.date_range("2024-01-01", periods=250, freq="B")
    np.random.seed(42)
    close = np.cumsum(np.random.randn(250) * 0.5) + 400
    return pd.DataFrame({
        "Open": close - np.random.uniform(0, 2, 250),
        "High": close + np.random.uniform(0, 3, 250),
        "Low": close - np.random.uniform(0, 3, 250),
        "Close": close,
        "Volume": np.random.randint(10_000_000, 50_000_000, 250),
    }, index=dates)


def _mock_alpha_response():
    """Create a realistic mock Alpha Vantage response."""
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    np.random.seed(42)
    close = np.cumsum(np.random.randn(100) * 0.5) + 400
    return [
        {
            "date": d.to_pydatetime(),
            "open": round(c - np.random.uniform(0, 2), 2),
            "high": round(c + np.random.uniform(0, 3), 2),
            "low": round(c - np.random.uniform(0, 3), 2),
            "close": round(c, 2),
            "volume": int(np.random.randint(10_000_000, 50_000_000)),
        }
        for d, c in zip(dates, close)
    ]


@patch("historicals.get_hist_data_from_yahoo")
def test_get_historical_data_yahoo(mock_yahoo):
    mock_yahoo.return_value = _mock_yahoo_dataframe()
    data = get_historical_data(symbol, force_source="yahoo")
    assert data is not None
    assert not data.empty
    assert "open" in data.columns or "Open" in data.columns
    mock_yahoo.assert_called_once_with(symbol)


@patch("historicals.get_symbol_history_from_alpha")
def test_get_historical_data_alpha(mock_alpha):
    mock_alpha.return_value = _mock_alpha_response()
    data = get_historical_data(symbol, force_source="alpha")
    assert data is not None
    assert not data.empty
    assert all(col in data.columns for col in ['date', 'open', 'high', 'low', 'close', 'volume'])
    mock_alpha.assert_called_once_with(symbol, 1825)


@patch("historicals.get_hist_data_from_yahoo")
@patch("historicals.get_symbol_history_from_alpha")
def test_yahoo_fallback_to_alpha(mock_alpha, mock_yahoo):
    """When Yahoo returns None, should fall back to Alpha Vantage."""
    mock_yahoo.return_value = None
    mock_alpha.return_value = _mock_alpha_response()
    data = get_historical_data(symbol)
    assert data is not None
    assert not data.empty
    mock_yahoo.assert_called_once()
    mock_alpha.assert_called_once()


def test_create_hist_data():
    df = create_hist_data()
    assert df is not None
    assert not df.empty
    assert len(df) == 20
    assert all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume', 'date'])


def test_parse_data_yahoo():
    yahoo_df = _mock_yahoo_dataframe()
    result = parse_data({"yahoo": yahoo_df})
    assert result is not None
    assert "date" in result.columns
    assert "close" in result.columns


def test_parse_data_alpha():
    alpha_data = _mock_alpha_response()
    result = parse_data({"alpha": alpha_data})
    assert result is not None
    assert "date" in result.columns
    assert "close" in result.columns


def test_parse_data_none_source():
    result = parse_data({"yahoo": None})
    assert result is None
