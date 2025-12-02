import requests
import httpx
from openai import OpenAI
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)

def check_llm_env():
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY is not defined in the environment.")

    if not os.getenv('LLM_MODEL_NAME') :
        logger.error("LLM_MODEL_NAME is not defined in the environment.")

    if not os.getenv('REVENUE_PERCENTAGE') :
        logger.warning("REVENUE_PERCENTAGE is not defined")

if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

def get_llm_file_analysis():
    # TODO: upload the file to openAI
    raise ("to be defined")

def get_llm_signals_analysis(signals, symbol, current_price):
    """
    Query the LLM model with stock signals and get a concise buy/hold/sell recommendation.
    
    Parameters:
    - signals: dict of financial indicators (e.g., SMA_50, RSI, MACD)
    - symbol: ticker symbol string
    - current_price: current stock price (not used here but may be useful)
    
    Returns:
    - LLM-generated text recommendation or error message string
    """
    check_llm_env()

    model_name = os.getenv('LLM_MODEL_NAME', 'gpt-4o') 
    revenue_percentage = os.getenv('REVENUE_PERCENTAGE') 
    
    logger.info(f"Calling LLM model {model_name}...")

    # Prepare metrics string from signals dictionary
    metrics = "\n".join([f"{signal} = {value} " for signal, value in signals.items()])

    prompt = (
        f"Return a clear answer about the symbol using these historical metrics:\n{metrics} and current_price:{current_price}\n\n"
        f"Goal: identify short-term bullish setups (1–4 weeks) potentially capable of yielding ~{revenue_percentage}% profit.\n"
        f"Output format: DECISION - brief explanation (max 30 words, include indicators in parentheses).\n"
        f"Options for DECISION: SELL, HOLD, BUY, EMPTY_DECISION."
    )

    try:
        openai = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            http_client=httpx.Client(verify=False)
        )
        llm_temperature = 0

        messages_prompt = [
            {"role": "system", "content": "You are a financial assistant providing buy, hold or sell advice based on given metrics."},
            {"role": "user", "content": prompt}
        ]

        response = openai.chat.completions.create(
            model=model_name,
            messages=messages_prompt,
            temperature=llm_temperature
        )

        return response.choices[0].message.content

    except Exception as e:
        error_msg = f"Error getting LLM analysis for {symbol}: {e}"
        logger.error(error_msg)
        return error_msg
