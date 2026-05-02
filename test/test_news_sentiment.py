import sys
import os
import pytest
import requests
from unittest.mock import patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from tools.news_sentiment import (
    get_company_news,
    get_upcoming_earnings,
    analyze_news_sentiment_with_llm,
    _parse_sentiment_response,
    evaluate_news_filter,
)


# ─── Mock data ───────────────────────────────────────────────

MOCK_NEWS = [
    {
        "datetime": 1714600000,
        "headline": "AAPL beats Q2 earnings expectations with strong iPhone sales",
        "source": "Reuters",
        "url": "https://example.com/1",
    },
    {
        "datetime": 1714500000,
        "headline": "Apple announces $110 billion share buyback program",
        "source": "Bloomberg",
        "url": "https://example.com/2",
    },
]

MOCK_NEWS_NEGATIVE = [
    {
        "datetime": 1714600000,
        "headline": "SEC launches investigation into company accounting practices",
        "source": "WSJ",
        "url": "https://example.com/3",
    },
    {
        "datetime": 1714500000,
        "headline": "CEO resigns amid fraud allegations",
        "source": "Reuters",
        "url": "https://example.com/4",
    },
]

MOCK_EARNINGS = {
    "earningsCalendar": [
        {
            "date": "2025-05-05",
            "epsActual": None,
            "epsEstimate": 1.5,
            "symbol": "AAPL",
        }
    ]
}


# ─── Tests: _parse_sentiment_response ────────────────────────

def test_parse_positive_sentiment():
    result = _parse_sentiment_response("POSITIVE 80% - Strong earnings beat and buyback announcement")
    assert result["sentiment"] == "POSITIVE"
    assert result["confidence"] == 0.8
    assert "earnings" in result["summary"].lower()


def test_parse_negative_sentiment():
    result = _parse_sentiment_response("NEGATIVE 90% - SEC investigation and CEO resignation")
    assert result["sentiment"] == "NEGATIVE"
    assert result["confidence"] == 0.9


def test_parse_neutral_sentiment():
    result = _parse_sentiment_response("NEUTRAL 50% - Mixed signals, no clear direction")
    assert result["sentiment"] == "NEUTRAL"
    assert result["confidence"] == 0.5


def test_parse_malformed_response():
    result = _parse_sentiment_response("some random text without format")
    assert result["sentiment"] == "NEUTRAL"
    assert result["confidence"] == 0.5


# ─── Tests: get_company_news ─────────────────────────────────

@patch("tools.news_sentiment.requests.get")
def test_get_company_news_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_NEWS
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = get_company_news("AAPL")
    assert len(result) == 2
    assert result[0]["headline"] == MOCK_NEWS[0]["headline"]


@patch("tools.news_sentiment.requests.get")
def test_get_company_news_failure(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("Connection error")

    result = get_company_news("AAPL")
    assert result == []


@patch("tools.news_sentiment.requests.get")
def test_get_company_news_empty(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = get_company_news("UNKNOWN")
    assert result == []


# ─── Tests: get_upcoming_earnings ────────────────────────────

@patch("tools.news_sentiment.requests.get")
def test_get_upcoming_earnings_found(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_EARNINGS
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = get_upcoming_earnings("AAPL")
    assert result is not None
    assert result["date"] == "2025-05-05"


@patch("tools.news_sentiment.requests.get")
def test_get_upcoming_earnings_none(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"earningsCalendar": []}
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = get_upcoming_earnings("MSFT")
    assert result is None


@patch("tools.news_sentiment.requests.get")
def test_get_upcoming_earnings_failure(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout("Timeout")

    result = get_upcoming_earnings("AAPL")
    assert result is None


# ─── Tests: evaluate_news_filter ─────────────────────────────

@patch("tools.news_sentiment.get_upcoming_earnings")
def test_filter_blocks_on_earnings(mock_earnings):
    mock_earnings.return_value = {"date": "2025-05-05", "symbol": "AAPL"}

    result = evaluate_news_filter("AAPL", news_sentiment_enabled=True)
    assert result["block_buy"] is True
    assert result["earnings_soon"] is True
    assert "Earnings" in result["reason"]


@patch("tools.news_sentiment.analyze_news_sentiment_with_llm")
@patch("tools.news_sentiment.get_company_news")
@patch("tools.news_sentiment.get_upcoming_earnings")
def test_filter_blocks_on_negative_news(mock_earnings, mock_news, mock_sentiment):
    mock_earnings.return_value = None
    mock_news.return_value = MOCK_NEWS_NEGATIVE
    mock_sentiment.return_value = {
        "sentiment": "NEGATIVE",
        "confidence": 0.85,
        "summary": "SEC investigation and CEO resignation",
    }

    result = evaluate_news_filter("BADCO", news_sentiment_enabled=True)
    assert result["block_buy"] is True
    assert "Negative news" in result["reason"]


@patch("tools.news_sentiment.get_company_news")
@patch("tools.news_sentiment.get_upcoming_earnings")
def test_filter_passes_when_disabled(mock_earnings, mock_news):
    mock_earnings.return_value = None

    result = evaluate_news_filter("AAPL", news_sentiment_enabled=False)
    assert result["block_buy"] is False
    assert "disabled" in result["news_sentiment"]["summary"].lower()
    # get_company_news should NOT have been called
    mock_news.assert_not_called()


@patch("tools.news_sentiment.analyze_news_sentiment_with_llm")
@patch("tools.news_sentiment.get_company_news")
@patch("tools.news_sentiment.get_upcoming_earnings")
def test_filter_allows_positive_news(mock_earnings, mock_news, mock_sentiment):
    mock_earnings.return_value = None
    mock_news.return_value = MOCK_NEWS
    mock_sentiment.return_value = {
        "sentiment": "POSITIVE",
        "confidence": 0.8,
        "summary": "Strong earnings and buyback",
    }

    result = evaluate_news_filter("AAPL", news_sentiment_enabled=True)
    assert result["block_buy"] is False


@patch("tools.news_sentiment.get_company_news")
@patch("tools.news_sentiment.get_upcoming_earnings")
def test_filter_allows_no_news(mock_earnings, mock_news):
    mock_earnings.return_value = None
    mock_news.return_value = []

    result = evaluate_news_filter("NEWCO", news_sentiment_enabled=True)
    assert result["block_buy"] is False
    assert "No recent news" in result["news_sentiment"]["summary"]


@patch("tools.news_sentiment.analyze_news_sentiment_with_llm")
@patch("tools.news_sentiment.get_company_news")
@patch("tools.news_sentiment.get_upcoming_earnings")
def test_filter_allows_low_confidence_negative(mock_earnings, mock_news, mock_sentiment):
    """Negative sentiment with low confidence (<0.7) should NOT block BUY."""
    mock_earnings.return_value = None
    mock_news.return_value = MOCK_NEWS_NEGATIVE
    mock_sentiment.return_value = {
        "sentiment": "NEGATIVE",
        "confidence": 0.5,
        "summary": "Some concerns but unclear impact",
    }

    result = evaluate_news_filter("MAYBE", news_sentiment_enabled=True)
    assert result["block_buy"] is False
