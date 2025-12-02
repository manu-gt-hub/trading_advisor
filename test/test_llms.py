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
        "ROC_10": 0.0559,
        "Volatility_20": 0.0317,
        "ATR_14": 9.307,
        "Breakout_20": 0.0,
        "Monthly_10pct_Prob": 0.2739,
        "Current_Price": 150.0
    }

    symbol = "AAPL"

    # Call the function under test
    result = get_llm_signals_analysis(signals, symbol)

    # Basic validations
    assert isinstance(result, str), "The LLM response should be a string."
    assert len(result) > 0, "The LLM response should not be empty."

    # Ensure the output follows the 'DECISION - explanation' format
    assert " - " in result, "Output should follow the format: DECISION - explanation."

    # Extract DECISION part
    decision = result.split(" - ")[0].strip().upper()

    # Valid decisions allowed by spec
    valid_decisions = {"BUY", "HOLD", "SELL", "EMPTY_DECISION"}
    assert decision in valid_decisions, f"Decision '{decision}' is not valid."

    # Ensure explanation is present and not empty
    explanation = result.split(" - ", 1)[1].strip()
    assert len(explanation) > 0, "Explanation should not be empty."

    # Enforce 30-word max per prompt specifications
    word_count = len(result.split())
    assert word_count <= 30, f"LLM output exceeds 30 words (found {word_count})."
