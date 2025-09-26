# test/test_historicals.py

import sys
import os
import pytest
import warnings
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from historicals import get_historical_data, create_hist_data

symbol = "MSFT"

def test_get_historical_data_yahoo():
    data = get_historical_data(symbol, force_source="yahoo")

    if data is None or data.empty:
        warnings.warn("Yahoo returned no data or empty DataFrame")
    else:
        assert all(col in data.columns for col in ['date', 'open', 'high', 'low', 'close', 'volume'])



def test_get_historical_data_alpha():

    data = get_historical_data(symbol, force_source="alpha")
    assert data is not None, "No data returned from Alpha Vantage"
    assert not data.empty, "Returned DataFrame from Alpha is empty"
    assert all(col in data.columns for col in ['date', 'open', 'high', 'low', 'close', 'volume'])


def test_create_hist_data():
    df = create_hist_data()
    assert df is not None
    assert not df.empty
    assert len(df) == 20
    assert all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume', 'date'])
