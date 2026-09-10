import sys
import os
import pytest
import warnings
from unittest.mock import patch, Mock, MagicMock
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from llms import (
    get_gpt_signals_analysis, get_deepseek_signals_analysis,
    parse_audit_response, audit_buy_signal, generate_audit_prompt,
)

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


# ---------------------------------------------------------------------------
# parse_audit_response — tests the REAL parsing logic, not mocks
# ---------------------------------------------------------------------------
class TestParseAuditResponse:

    def test_coherent_with_positive_adjustment(self):
        text = "COHERENT | adjustment=0.05 | indicators align well"
        result = parse_audit_response(text, bounds=(-0.3, 0.1))
        assert result["coherent"] is True
        assert result["adjustment"] == 0.05
        assert "indicators align" in result["reason"]

    def test_incoherent_with_negative_adjustment(self):
        text = "INCOHERENT | adjustment=-0.15 | RSI overbought contradicts BUY"
        result = parse_audit_response(text, bounds=(-0.3, 0.1))
        assert result["coherent"] is False
        assert result["adjustment"] == -0.15

    def test_adjustment_clamped_to_bounds(self):
        text = "COHERENT | adjustment=0.5 | everything perfect"
        result = parse_audit_response(text, bounds=(-0.3, 0.1))
        assert result["adjustment"] == 0.1  # clamped to upper bound

        text2 = "INCOHERENT | adjustment=-0.8 | terrible setup"
        result2 = parse_audit_response(text2, bounds=(-0.3, 0.1))
        assert result2["adjustment"] == -0.3  # clamped to lower bound

    def test_unparseable_response_defaults(self):
        text = "This is complete garbage from a confused LLM"
        result = parse_audit_response(text, bounds=(-0.3, 0.1))
        assert result["coherent"] is True  # safe default
        assert result["adjustment"] == 0.0  # no adjustment
        assert result["raw"] == text

    def test_none_input(self):
        result = parse_audit_response(None, bounds=(-0.3, 0.1))
        assert result["coherent"] is True
        assert result["adjustment"] == 0.0

    def test_empty_string(self):
        result = parse_audit_response("", bounds=(-0.3, 0.1))
        assert result["coherent"] is True
        assert result["adjustment"] == 0.0


# ---------------------------------------------------------------------------
# audit_buy_signal — test with mocked OpenAI to verify real logic path
# ---------------------------------------------------------------------------
class TestAuditBuySignal:

    _technical_result = {
        "signal": "BUY",
        "strength": "MODERATE",
        "regime": "TRENDING_UP",
        "sub_scores": {"trend_score": 0.6, "momentum_score": 0.5, "risk_score": 0.3},
        "factors": {},
    }

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "fake-key",
        "GPT_MODEL_NAME": "gpt-4o",
        "REVENUE_PERCENTAGE": "10",
    })
    @patch("llms.OpenAI")
    def test_coherent_audit_returns_positive_adjustment(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "COHERENT | adjustment=0.05 | all indicators confirm BUY"
        mock_client.chat.completions.create.return_value = mock_response

        result = audit_buy_signal(signals, "AAPL", 155.0, self._technical_result)
        assert result["coherent"] is True
        assert result["adjustment"] == 0.05
        assert "confirm BUY" in result["reason"]

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "fake-key",
        "GPT_MODEL_NAME": "gpt-4o",
        "REVENUE_PERCENTAGE": "10",
    })
    @patch("llms.OpenAI")
    def test_incoherent_audit_returns_negative_adjustment(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "INCOHERENT | adjustment=-0.2 | bearish divergence not reflected in score"
        mock_client.chat.completions.create.return_value = mock_response

        result = audit_buy_signal(signals, "AAPL", 155.0, self._technical_result)
        assert result["coherent"] is False
        assert result["adjustment"] == -0.2

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "fake-key",
        "GPT_MODEL_NAME": "gpt-4o",
        "REVENUE_PERCENTAGE": "10",
    })
    @patch("llms.OpenAI")
    def test_api_failure_returns_conservative_result(self, mock_openai_class):
        """When the LLM API fails, the system should fail conservatively (incoherent, max penalty)."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API timeout")

        result = audit_buy_signal(signals, "AAPL", 155.0, self._technical_result)
        # Must NOT assume coherent on error
        assert result["coherent"] is False
        # Must apply max negative adjustment (lower bound)
        assert result["adjustment"] < 0
        assert "audit error" in result["reason"]
