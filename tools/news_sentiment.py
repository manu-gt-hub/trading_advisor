import os
import requests
import logging
from datetime import datetime, timedelta
from openai import OpenAI
import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

if not os.getenv("GITHUB_ACTIONS"):
    load_dotenv()

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY")
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def get_company_news(symbol, days_back=7):
    """
    Fetch recent news for a symbol from Finnhub.
    Returns a list of news dicts or empty list on failure.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = f"{FINNHUB_BASE_URL}/company-news"
    params = {
        "symbol": symbol,
        "from": from_date,
        "to": today,
        "token": FINNHUB_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        news = response.json()

        if not isinstance(news, list):
            logger.warning(f"⚠️ Unexpected news response for {symbol}: {news}")
            return []

        logger.info(f"📰 Fetched {len(news)} news articles for {symbol}")
        return news

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to fetch news for {symbol}: {e}")
        return []


def get_upcoming_earnings(symbol, days_ahead=5):
    """
    Check if a symbol has earnings scheduled within the next N days.
    Returns dict with earnings info or None if no upcoming earnings.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    to_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    url = f"{FINNHUB_BASE_URL}/calendar/earnings"
    params = {
        "symbol": symbol,
        "from": today,
        "to": to_date,
        "token": FINNHUB_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        earnings = data.get("earningsCalendar", [])
        if earnings:
            next_earnings = earnings[0]
            logger.info(f"📅 {symbol} has earnings on {next_earnings.get('date')}")
            return next_earnings

        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to fetch earnings calendar for {symbol}: {e}")
        return None


def analyze_news_sentiment_with_llm(symbol, news_articles, max_articles=10):
    """
    Use GPT to analyze sentiment of recent news headlines for a symbol.
    Returns a dict with sentiment, confidence, and summary.
    """
    if not news_articles:
        return {"sentiment": "NEUTRAL", "confidence": 0.5, "summary": "No recent news found."}

    # Take the most recent articles and extract headlines
    recent = news_articles[:max_articles]
    headlines = "\n".join(
        [f"- [{a.get('datetime', '')}] {a.get('headline', 'No headline')}" for a in recent]
    )

    model_name = os.getenv("GPT_MODEL_NAME", "gpt-4o")

    prompt = (
        f"Analyze the sentiment of these recent news headlines for {symbol}:\n\n"
        f"{headlines}\n\n"
        f"Rules:\n"
        f"- Focus on how these news items would affect the stock price in the next 1-4 weeks.\n"
        f"- Ignore generic market news that doesn't specifically impact {symbol}.\n"
        f"- Consider: earnings surprises, lawsuits, FDA approvals, analyst upgrades/downgrades, "
        f"product launches, management changes, regulatory issues.\n\n"
        f"Output format (exactly one line):\n"
        f"SENTIMENT CONFIDENCE% - brief explanation (max 20 words)\n"
        f"SENTIMENT options: POSITIVE, NEGATIVE, NEUTRAL\n"
        f"CONFIDENCE: 0-100 (how sure you are about the sentiment direction)\n"
        f"Example: NEGATIVE 85% - CEO resignation and SEC investigation create significant downside risk"
    )

    try:
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            http_client=httpx.Client(verify=False),
        )

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a financial news sentiment analyst. "
                        "You evaluate how news headlines affect stock prices. "
                        "Be concise and precise."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )

        answer = response.choices[0].message.content.strip()
        logger.info(f"📰 News sentiment for {symbol}: {answer}")

        return _parse_sentiment_response(answer)

    except Exception as e:
        logger.error(f"❌ Failed to analyze news sentiment for {symbol}: {e}")
        return {"sentiment": "NEUTRAL", "confidence": 0.5, "summary": f"LLM error: {e}"}


def _parse_sentiment_response(response_text):
    """Parse the LLM sentiment response into structured data."""
    try:
        parts = response_text.split("-", 1)
        first_part = parts[0].strip().upper()
        summary = parts[1].strip() if len(parts) > 1 else response_text

        sentiment = "NEUTRAL"
        for s in ["POSITIVE", "NEGATIVE", "NEUTRAL"]:
            if s in first_part:
                sentiment = s
                break

        confidence = 0.5
        for token in first_part.split():
            token_clean = token.strip().rstrip("%")
            try:
                val = float(token_clean)
                if 0 <= val <= 100:
                    confidence = val / 100.0
                    break
            except ValueError:
                continue

        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "summary": summary,
        }

    except Exception:
        return {
            "sentiment": "NEUTRAL",
            "confidence": 0.5,
            "summary": response_text,
        }


def evaluate_news_filter(symbol, news_sentiment_enabled=True):
    """
    Evaluate whether a symbol should be blocked from BUY based on news.
    Returns a dict with:
      - block_buy: bool — True if BUY should be blocked
      - reason: str — explanation
      - earnings_soon: bool
      - news_sentiment: dict with sentiment details
    """
    result = {
        "block_buy": False,
        "reason": "",
        "earnings_soon": False,
        "news_sentiment": {"sentiment": "NEUTRAL", "confidence": 0.5, "summary": "Analysis disabled."},
    }

    # Always check earnings (cheap API call, no LLM needed)
    earnings = get_upcoming_earnings(symbol, days_ahead=5)
    if earnings:
        result["earnings_soon"] = True
        result["block_buy"] = True
        earnings_date = earnings.get("date", "unknown")
        result["reason"] = f"Earnings scheduled on {earnings_date} — avoid buying before earnings."
        logger.warning(f"🚫 {symbol}: BUY blocked — earnings on {earnings_date}")
        return result

    # News sentiment analysis (only if flag is enabled)
    if not news_sentiment_enabled:
        result["news_sentiment"]["summary"] = "News sentiment analysis disabled."
        return result

    news = get_company_news(symbol, days_back=7)
    if not news:
        result["news_sentiment"]["summary"] = "No recent news found."
        return result

    sentiment = analyze_news_sentiment_with_llm(symbol, news)
    result["news_sentiment"] = sentiment

    # Block BUY if sentiment is strongly negative
    if sentiment["sentiment"] == "NEGATIVE" and sentiment["confidence"] >= 0.7:
        result["block_buy"] = True
        result["reason"] = f"Negative news sentiment ({sentiment['confidence']:.0%}): {sentiment['summary']}"
        logger.warning(f"🚫 {symbol}: BUY blocked — {result['reason']}")

    return result
