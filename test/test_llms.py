import sys
import os
import pytest
import warnings
from unittest.mock import patch, Mock, MagicMock
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from llms import parse_audit_response, audit_buy_signal, generate_audit_prompt

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
