# test_llms.py

import sys
import os
import pytest
import warnings
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from llms import get_llm_signals_analysis

def test_get_llm_analysis_basic():
    # Sample dummy signals
    signals = {
        "SMA_50": 100.5,
        "SMA_200": 98.3,
        "RSI": 45,
        "MACD": 1.2,
        "MACD_Signal": 1.1,
        "MACD_Hist": 0.1,
        "ROC_10" = 0.0559,
        "Volati2lity_20" = 0.0317,
        "ATR_14" = 9.307,
        "Breakout_20" = 0.0,
        "Monthly_10pct_Prob" = 0.2739,
        "Current_Price" = 150.0
    }
    symbol = "AAPL"
    current_price = 150.0

    result = get_llm_signals_analysis(signals, symbol)

    # The result should be a non-empty string
    assert isinstance(result, str)
    assert len(result) > 0
