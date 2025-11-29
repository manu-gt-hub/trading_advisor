import pandas as pd
import numpy as np
import re
import logging
from datetime import datetime
import pytz
import os
import csv

logger = logging.getLogger(__name__)

def get_mapping_string(symbol, csv_file_path='resources/investing_symbol_mapping.csv'):
    # Check if the CSV file exists
    if not os.path.exists(csv_file_path):
        print(f"Error: The file {csv_file_path} was not found.")
        return None

    try:
        # Open the CSV file for reading
        with open(csv_file_path, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)  # Use DictReader to work with headers

            # Iterate through the rows of the CSV file
            for row in reader:
                # Compare the symbol and return the mapping_string if there is a match
                if row['symbol'] == symbol:
                    return row['mapping_string']

        # If no match is found, return None
        print(f"The symbol {symbol} was not found in the CSV file.")
        return None

    except Exception as e:
        # Handle any exceptions that occur while reading the CSV file
        print(f"Error reading the CSV file: {e}")
        return None

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
    error_values = [None, 'error']

    # If both decisions are the same and valid, return it
    if tv_decision == llm_decision and (tv_decision not in error_values) and (llm_decision not in error_values):
        return tv_decision
    # If TV is invalid but LLM is valid, return LLM
    elif tv_decision in error_values and llm_decision not in error_values:
        return llm_decision
    # If LLM is invalid but TV is valid, return TV
    elif llm_decision in error_values and tv_decision not in error_values:
        return tv_decision
    # Otherwise, no clear decision
    else:
        return 'EMPTY_DECISION'

    

def generate_action_column(df: pd.DataFrame, opinion_type: str) -> pd.DataFrame:
    """
    Adds a 'action' column to the DataFrame based on matching logic
    between 'trading_view_opinion' and 'llm_opinion'.

    Parameters:
        df (pd.DataFrame): DataFrame containing 'trading_view_opinion' and 'llm_opinion' columns.
        force_opinion (str): Optionally force decision source: "LLM", "TV", or "CUSTOM".

    Returns:
        pd.DataFrame: Original DataFrame with 'action' column added.
    """
    # Clean force_opinion input
    opinion_type = opinion_type.strip().upper()
    logger.debug(f"Opinion type: {opinion_type}")

    if opinion_type == "TV":
        logger.debug("set decision logic as TV")

        df['action'] = df['trading_view_opinion'].apply(extract_trading_view_decision)

    elif opinion_type == "LLM":
        logger.debug("set decision logic as LLM")

        df['action'] = df['llm_opinion'].apply(extract_llm_decision)

    elif opinion_type == "CUSTOM":
        logger.debug("set decision logic as CUSTOM")

        df['action'] = df['manual_financial_analysis'].apply(extract_custom_decision)

    else:  # Default logic: compare both and apply decision logic
        logger.debug("set decision logic as DEFAULT")

        df['tv_decision'] = df['trading_view_opinion'].apply(extract_trading_view_decision)
        df['llm_decision'] = df['llm_opinion'].apply(extract_llm_decision)
        df['action'] = df.apply(
            lambda row: decide_final_action(row['tv_decision'], row['llm_decision']), axis=1
        )
        
        df = df.drop(columns=['tv_decision', 'llm_decision'])

    return df

def get_current_time_madrid():
    madrid_tz = pytz.timezone('Europe/Madrid')
    return datetime.now(madrid_tz).strftime("%Y-%m-%d %H:%M")
