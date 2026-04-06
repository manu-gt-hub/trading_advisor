import sys
import os
import pytest
import warnings
from unittest.mock import patch, Mock, MagicMock
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from llms import get_gpt_signals_analysis, get_deepseek_signals_analysis

symbol = "AAPL"
current_price = 155.0
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

FAKE_GPT_RESPONSE = "BUY - Strong bullish momentum with RSI (45) and positive MACD histogram (0.1)"
FAKE_DEEPSEEK_RESPONSE = "HOLD - Neutral signals with moderate volatility (0.0317) and flat breakout (0.0)"


@patch.dict(os.environ, {
    "OPENAI_API_KEY": "fake-api-key",
    "GPT_MODEL_NAME": "gpt-4o",
    "REVENUE_PERCENTAGE": "10",
})
@patch("llms.OpenAI")
def test_get_gpt_analysis_basic(mock_openai_class):
    # Configure the mock to return a fake LLM response
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = FAKE_GPT_RESPONSE
    mock_client.chat.completions.create.return_value = mock_response

    symbol = "AAPL"
    current_price = 150.0
    # Call the function under test
    result = get_gpt_signals_analysis(signals, symbol, current_price)

    # Verify OpenAI client was called
    mock_client.chat.completions.create.assert_called_once()

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


# Test for get_deepseek_signals_analysis

@patch.dict(os.environ, {
    "DEEPKSEEK_API_KEY": "fake-deepseek-key",
    "REVENUE_PERCENTAGE": "10",
})
@patch("llms.requests.post")
def test_get_deepseek_analysis(mock_post):
    # Configure the mock to return a fake DeepSeek API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": FAKE_DEEPSEEK_RESPONSE}}]
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    # Call the real function that makes the request to the DeepSeek API
    result = get_deepseek_signals_analysis(signals, symbol, current_price)

    # Verify the HTTP call was made
    mock_post.assert_called_once()

    # Basic validations
    assert isinstance(result, str), "The DeepSeek response should be a string."
    assert len(result) > 0, "The DeepSeek response should not be empty."

    # Ensure the output follows the 'DECISION - explanation' format
    assert " - " in result, "Output should follow the format: DECISION - explanation."

    # Extract the DECISION part
    decision = result.split(" - ")[0].strip().upper()

    # Valid decisions allowed by the specification
    valid_decisions = {"BUY", "HOLD", "SELL", "EMPTY_DECISION"}
    assert decision in valid_decisions, f"Decision '{decision}' is not valid."

    # Ensure there is an explanation and it is not empty
    explanation = result.split(" - ", 1)[1].strip()
    assert len(explanation) > 0, "Explanation should not be empty."

    # Enforce a maximum of 30 words as per prompt specifications
    word_count = len(result.split())
    assert word_count <= 30, f"DeepSeek output exceeds 30 words (found {word_count})."
