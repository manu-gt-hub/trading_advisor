import requests
import httpx
from openai import OpenAI

def get_llm_file_analysis():
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

    model_name = "gpt-4o-mini"
    print(f"Calling LLM model {model_name}...")

    # Prepare metrics string from signals dictionary
    metrics = "\n".join([f"{signal} = {value}" for signal, value in signals.items()]) + "\n"

    prompt = (
        f"Return me a clear answer about the provided symbol and the following metrics taken from its historical data: {metrics}"
        f"Take a look at the indicators: SMA_50, SMA_200, RSI, MACD, MACD_Signal, MACD_Hist. "
        f"My intention when buying is to get a profit of 10-12% within the next month. "
        f"The answer has to be: 'sell', 'hold', 'buy', or 'empty decision' "
        f"(in case there is no clear decision or insufficient input data), "
        f"and a brief explanation in a few words (max. 20). "
        f"After the explanation, please print the indicators between parentheses."
    )
    print(f"Prompt: {prompt}")

    try:
        openai = OpenAI(http_client=httpx.Client(verify=False))
        llm_temperature = 0.1

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
        error_msg = f"Error while getting LLM analysis for symbol {symbol}: {e}"
        print(error_msg)
        return error_msg
