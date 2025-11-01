import pandas as pd
import numpy as np
import re
import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

def add_opinion(symbol,df,new_column_name,opinion):
    df.loc[df['symbol'] == symbol, new_column_name] = opinion

def parse_transactions_df(df):
    parsed_df = df.copy()

    # convert dates
    parsed_df['buy_date'] = pd.to_datetime(parsed_df['buy_date'], errors='coerce')
    parsed_df['sell_date'] = pd.to_datetime(parsed_df['sell_date'], errors='coerce')

    # convert to nums
    parsed_df['current_price'] = pd.to_numeric(parsed_df['current_price'], errors='coerce')
    parsed_df['sell_value'] = pd.to_numeric(parsed_df['sell_value'], errors='coerce')
    parsed_df['percentage_benefit'] = pd.to_numeric(parsed_df['percentage_benefit'], errors='coerce')
    parsed_df['buy_sell_days_diff'] = pd.to_numeric(parsed_df['buy_sell_days_diff'], errors='coerce').astype('Int64')  # permite NaN

    return parsed_df

# Function to extract the dominant opinion from trading_view_opinion
def extract_trading_view_decision(opinion):
    if opinion == None:
        return "error"
    
    matches = re.findall(r'(\w+)\s+\((\d+)\)', opinion)
    if not matches:
        return None
    matches = [(op.upper(), int(score)) for op, score in matches]
    return max(matches, key=lambda x: x[1])[0]  # Returns 'SELL', 'BUY', etc.

# Function to extract the decision from llm_op
def extract_llm_decision(opinion):
    if not isinstance(opinion, str):
        return None
    return opinion.split('-')[0].strip().upper()  # Returns 'SELL', 'BUY', etc.

def extract_custom_decision(opinion):
    if not isinstance(opinion, str):
        return None
    return opinion.split(' ')[1].strip().upper()  # Returns 'SELL', 'BUY', etc.

# Function to decide final action based on both opinions
def decide_final_action(tv_decision, llm_decision):
    if tv_decision == llm_decision:
        return tv_decision
    elif (tv_decision is None or tv_decision == 'error') and llm_decision is not None:
        return llm_decision
    elif tv_decision is not None and (llm_decision is None or llm_decision == 'error'):
        return tv_decision
    else:
        return 'EMPTY_DECISION'
    

def generate_decision_column(df: pd.DataFrame, opinion_type: str) -> pd.DataFrame:
    """
    Adds a 'decision' column to the DataFrame based on matching logic
    between 'trading_view_opinion' and 'llm_opinion'.

    Parameters:
        df (pd.DataFrame): DataFrame containing 'trading_view_opinion' and 'llm_opinion' columns.
        force_opinion (str): Optionally force decision source: "LLM", "TV", or "CUSTOM".

    Returns:
        pd.DataFrame: Original DataFrame with 'decision' column added.
    """
    # Clean force_opinion input
    opinion_type = opinion_type.upper()
    logger.debug(f"Opinion type: {opinion_type}")

    if opinion_type == "TV":
        df['decision'] = df['trading_view_opinion'].apply(extract_trading_view_decision)

    elif opinion_type == "LLM":
        df['decision'] = df['llm_opinion'].apply(extract_llm_decision)

    elif opinion_type == "CUSTOM":
        df['decision'] = df['manual_financial_analysis'].apply(extract_custom_decision)

    else:  # Default logic: compare both and apply decision logic
        df['tv_decision'] = df['trading_view_opinion'].apply(extract_trading_view_decision)
        df['llm_decision'] = df['llm_opinion'].apply(extract_llm_decision)
        df['decision'] = df.apply(
            lambda row: decide_final_action(row['tv_decision'], row['llm_decision']), axis=1
        )
        df = df.drop(columns=['tv_decision', 'llm_decision'])

    return df

def get_current_time_madrid():
    madrid_tz = pytz.timezone('Europe/Madrid')
    return datetime.now(madrid_tz).strftime("%Y-%m-%d %H:%M")
