import requests
import httpx
from openai import OpenAI
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)

system_prompt = (
    "You are an expert short-term stock trading analyst. "
    "You analyze technical indicators to identify high-probability setups for 1-4 week trades. "
    "You are conservative: you only recommend BUY when multiple strong signals align (trend + momentum + confirmation). "
    "You recommend SELL when bearish signals dominate. "
    "You recommend HOLD when signals are mixed or inconclusive. "
    "Never recommend BUY in a bearish trend unless there is a clear reversal pattern. "
    "Never recommend SELL in a strong bullish trend unless overbought signals are extreme."
)

def generate_prompt(metrics, current_price, technical_evaluation=None, confidence=None):
    revenue_percentage = os.getenv('REVENUE_PERCENTAGE') 
    if not revenue_percentage:
        logger.warning("REVENUE_PERCENTAGE is not defined in the environment.")

    # Build context about the technical evaluation if available
    tech_context = ""
    if technical_evaluation and confidence is not None:
        tech_context = (
            f"\nOur quantitative model rates this stock as: {technical_evaluation} "
            f"(confidence: {confidence:.2f}, scale -1 to 1).\n"
            f"Use this as a reference but form your own independent judgment.\n"
        )

    return (
        f"Analyze the following technical indicators for a stock currently priced at {current_price}:\n"
        f"{metrics}\n"
        f"{tech_context}\n"
        f"KEY RULES:\n"
        f"- Goal: identify short-term setups (1-4 weeks) capable of ~{revenue_percentage}% profit.\n"
        f"- BUY only if trend (MA50>MA200, price>EMA20) AND momentum (RSI 55-70, MACD bullish) align.\n"
        f"- SELL if bearish trend AND weak momentum AND no reversal signs.\n"
        f"- HOLD if signals are mixed, conflicting, or insufficient for a strong conviction.\n"
        f"- When in doubt, prefer HOLD over BUY. Avoiding bad trades matters more than catching every opportunity.\n\n"
        f"Output format: DECISION - brief explanation (max 30 words, include key indicators in parentheses).\n"
        f"Options for DECISION: BUY, HOLD, SELL."
    )

def check_llm_env():
    """
    Ensure the necessary environment variables are set for the LLM API key, model name, and revenue percentage.
    """
    missing_env_vars = []
    
    if not os.getenv("OPENAI_API_KEY"):
        missing_env_vars.append("OPENAI_API_KEY")

    if not os.getenv('GPT_MODEL_NAME'):
        missing_env_vars.append("GPT_MODEL_NAME")

    if not os.getenv('REVENUE_PERCENTAGE'):
        missing_env_vars.append("REVENUE_PERCENTAGE")

    if missing_env_vars:
        logger.error(f"Missing environment variables: {', '.join(missing_env_vars)}")
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_env_vars)}")

if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

def get_llm_file_analysis():
    # Placeholder for uploading a file to OpenAI
    logger.warning("get_llm_file_analysis function is not yet implemented.")
    raise NotImplementedError("Function 'get_llm_file_analysis' is not implemented yet.")

def get_deepseek_signals_analysis(signals, symbol, current_price, technical_evaluation=None, confidence=None):
    API_KEY = os.getenv("DEEPKSEEK_API_KEY")
    if not API_KEY:
        logger.error("DEEPKSEEK_API_KEY is not defined in the environment.")
        return "Missing DEEPKSEEK_API_KEY"

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    metrics = "\n".join([f"{signal} = {value} " for signal, value in signals.items()])
    prompt = generate_prompt(metrics, current_price, technical_evaluation, confidence)

    data = {
        "model": "deepseek-reasoner",  # Use 'deepseek-reasoner' for R1 model or 'deepseek-chat' for V3 model
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "stream": False  # Disable streaming
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()  # Will raise HTTPError for bad responses (4xx or 5xx)

        result = response.json()
        return result['choices'][0]['message']['content']

    except requests.exceptions.RequestException as e:
        logger.error(f"DeepSeek Request failed for symbol {symbol}: {e}")
        return f"error {str(e)}"

def get_gpt_signals_analysis(signals, symbol, current_price, technical_evaluation=None, confidence=None):
    """
    Query the LLM model with stock signals and get a concise buy/hold/sell recommendation.
    
    Parameters:
    - signals: dict of financial indicators (e.g., SMA_50, RSI, MACD)
    - symbol: ticker symbol string
    - current_price: current stock price
    - technical_evaluation: optional string (BUY/HOLD/SELL) from quantitative model
    - confidence: optional float (-1 to 1) from quantitative model
    
    Returns:
    - LLM-generated text recommendation or error message string
    """
    check_llm_env()

    model_name = os.getenv('GPT_MODEL_NAME', 'gpt-4o') 
    
    logger.info(f"Calling GPT model {model_name}...")

    # Prepare metrics string from signals dictionary
    metrics = "\n".join([f"{signal} = {value} " for signal, value in signals.items()])
    prompt = generate_prompt(metrics, current_price, technical_evaluation, confidence)

    try:
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            http_client=httpx.Client(verify=False)
        )
        llm_temperature = 0

        messages_prompt = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        logger.info(f"LLM prompt sent: {prompt}")

        response = client.chat.completions.create(
            model=model_name,
            messages=messages_prompt,
            temperature=llm_temperature
        )

        llm_answer = response.choices[0].message.content

        logger.info(f"LLM answer: {llm_answer}")

        return llm_answer

    except Exception as e:
        error_msg = f"Error getting GPT analysis for {symbol}: {e}"
        logger.error(error_msg)
        return error_msg
