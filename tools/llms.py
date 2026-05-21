import requests
import httpx
from openai import OpenAI
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)

system_prompt = (
    "You are a critical risk reviewer for short-term stock trades (1-4 weeks). "
    "You challenge BUY recommendations by looking for hidden risks, but you also recognize genuinely strong setups. "
    "You receive technical indicators and a quantitative model's recommendation. "
    "Your role is to find what could go WRONG — but if the setup survives your scrutiny, confirm the BUY. "
    "Look for: divergences between indicators, overbought conditions masked by trend, "
    "volume anomalies, exhaustion patterns, false breakouts, and any red flags. "
    "Confirm BUY when trend, momentum, and volume align without significant contradictions. "
    "Recommend HOLD when you find real risks or contradictions that undermine the setup. "
    "Recommend SELL only if you see clear danger signs (breakdown, extreme overbought, distribution)."
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
        f"A quantitative model has analyzed a stock priced at {current_price} and produced these indicators:\n"
        f"{metrics}\n"
        f"{tech_context}\n"
        f"YOUR TASK: Review this setup critically. The target is ~{revenue_percentage}% profit in 1-4 weeks.\n"
        f"1. Look for risks the model might miss: divergences, overbought exhaustion, low volume breakouts, false signals.\n"
        f"2. Check if indicators CONFIRM each other or if there are hidden contradictions.\n"
        f"3. If the setup survives your scrutiny with no major red flags, confirm BUY.\n\n"
        f"DECISION RULES:\n"
        f"- BUY: Indicators align (trend + momentum + volume), no major contradictions or red flags found.\n"
        f"- HOLD: You found real risks or contradictions that weaken the setup significantly.\n"
        f"- SELL: Clear danger signs (breakdown, extreme overbought + distribution, bearish divergence).\n"
        f"- When in doubt between BUY and HOLD, prefer HOLD. But do not block solid setups without a concrete reason.\n\n"
        f"Output format: CONFIDENCE% DECISION - brief risk assessment (max 30 words, cite specific indicators).\n"
        f"CONFIDENCE is your conviction from 0 to 100. Options: BUY, HOLD, SELL."
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
