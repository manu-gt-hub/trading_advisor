import pandas as pd
import numpy as np
import re
import logging
from datetime import datetime
import pytz
import os
import csv
import json
from pathlib import Path

logger = logging.getLogger(__name__)

def get_mapping_string(symbol, csv_file_path='resources/investing_symbol_mapping.csv'):
    # Check if the CSV file exists
    if not os.path.exists(csv_file_path):
        logger.error(f"Error: The file {csv_file_path} was not found.")
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
        logger.warning(f"The symbol {symbol} was not found in the CSV file.")
        return None

    except Exception as e:
        # Handle any exceptions that occur while reading the CSV file
        logger.error(f"Error reading the CSV file: {e}")
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
# DEPRECATED DUE TO CAPTCHAS
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

def extract_custom_confidence(opinion):
    """Extract the confidence float from a custom label like '0.45 BUY'."""
    if not isinstance(opinion, str):
        return 0.0
    try:
        return float(opinion.split(' ')[0].strip())
    except (ValueError, IndexError):
        return 0.0

def apply_technical_filter(llm_decision, custom_opinion):
    """
    Apply the technical evaluation as a safety filter over the LLM decision.
    Rules:
      - If LLM says BUY but technical says SELL with confidence >= 0.3 → HOLD
      - If LLM says BUY but technical says HOLD with confidence >= 0.4 → HOLD
      - If LLM says SELL but technical says BUY with high confidence >= 0.5 → HOLD
      - Otherwise, trust the LLM decision
    """
    custom_decision = extract_custom_decision(custom_opinion)
    custom_conf = extract_custom_confidence(custom_opinion)

    error_values = [None, 'error', 'ERROR', 'EMPTY_DECISION', 'EVALUATION_FAILED']

    if llm_decision in error_values:
        return llm_decision

    if custom_decision in error_values:
        return llm_decision

    # LLM says BUY — technical can veto
    if llm_decision == 'BUY':
        if custom_decision == 'SELL' and custom_conf >= 0.3:
            logger.info(f"Technical filter: vetoed BUY → HOLD (technical={custom_decision}, conf={custom_conf:.2f})")
            return 'HOLD'
        if custom_decision == 'HOLD' and custom_conf >= 0.4:
            logger.info(f"Technical filter: vetoed BUY → HOLD (technical={custom_decision}, conf={custom_conf:.2f})")
            return 'HOLD'

    # LLM says SELL — technical can soften
    if llm_decision == 'SELL':
        if custom_decision == 'BUY' and custom_conf >= 0.5:
            logger.info(f"Technical filter: softened SELL → HOLD (technical={custom_decision}, conf={custom_conf:.2f})")
            return 'HOLD'

    return llm_decision

# Function to decide final action based on both opinions
def decide_final_action(llm_decision, llm_2_decision, custom_decision=None, custom_confidence=None):
    error_values = [None, 'error', 'ERROR', 'EMPTY_DECISION', 'EVALUATION_FAILED']

    llm_valid = llm_decision not in error_values
    llm2_valid = llm_2_decision not in error_values
    custom_valid = custom_decision not in error_values

    # Collect valid decisions
    valid_decisions = []
    if llm_valid:
        valid_decisions.append(llm_decision)
    if llm2_valid:
        valid_decisions.append(llm_2_decision)

    # If no valid LLM decisions, fall back to custom if available
    if not valid_decisions:
        if custom_valid:
            return custom_decision
        return 'EMPTY_DECISION'

    # If only one valid LLM decision
    if len(valid_decisions) == 1:
        single = valid_decisions[0]
        # If custom agrees or custom is unavailable, use the single LLM decision
        if not custom_valid or custom_decision == single:
            return single
        # LLM and custom disagree: conservative approach — prefer HOLD unless both say SELL
        if single == 'SELL' and custom_decision == 'SELL':
            return 'SELL'
        return 'HOLD'

    # Both LLMs are valid
    if llm_decision == llm_2_decision:
        return llm_decision

    # LLMs disagree: use custom as tiebreaker if available
    if custom_valid:
        # If custom agrees with either LLM, use that
        if custom_decision == llm_decision:
            return llm_decision
        elif custom_decision == llm_2_decision:
            return llm_2_decision
        # Custom disagrees with both: use custom with high confidence, else HOLD
        if custom_confidence is not None and abs(custom_confidence) >= 0.4:
            return custom_decision
        return 'HOLD'

    # LLMs disagree and no custom: conservative HOLD
    # Exception: if one says BUY and the other HOLD, prefer HOLD (conservative)
    # Exception: if one says SELL and the other HOLD, prefer SELL (risk management)
    decisions_set = {llm_decision, llm_2_decision}
    if decisions_set == {'SELL', 'HOLD'}:
        return 'SELL'
    if decisions_set == {'SELL', 'BUY'}:
        return 'HOLD'
    return 'HOLD'

    

def generate_action_column(df: pd.DataFrame, opinion_type: str) -> pd.DataFrame:
    """
    Adds a 'action' column to the DataFrame based on matching logic
    between 'llm_opinion' and 'llm_2_opinion'.

    Parameters:
        df (pd.DataFrame): DataFrame containing 'llm_opinion' and 'llm_2_opinion' columns.
        opinion_type (str): Optionally force decision source: "LLM1", "LLM2", or "CUSTOM".

    Returns:
        pd.DataFrame: Original DataFrame with 'action' column added.
    """
    # Clean force_opinion input
    opinion_type = opinion_type.strip().upper()
    logger.debug(f"Opinion type: {opinion_type}")

    if opinion_type == "LLM1":
        logger.debug("set decision logic as LLM-1 with technical filter")

        df['action'] = df['llm_opinion'].apply(extract_llm_decision)
        # Apply technical filter if manual_financial_analysis column exists
        if 'manual_financial_analysis' in df.columns:
            df['action'] = df.apply(
                lambda row: apply_technical_filter(row['action'], row['manual_financial_analysis']),
                axis=1
            )

    elif opinion_type == "LLM2":
        logger.debug("set decision logic as LLM-2")

        df['action'] = df['llm_2_opinion'].apply(extract_llm_decision)

    elif opinion_type == "CUSTOM":
        logger.debug("set decision logic as CUSTOM")

        df['action'] = df['manual_financial_analysis'].apply(extract_custom_decision)

    else:  # Default logic: compare both and apply decision logic
        logger.debug("set decision logic as DEFAULT")

        df['llm_opinion'] = df['llm_opinion'].apply(extract_llm_decision)
        df['llm_2_opinion'] = df['llm_2_opinion'].apply(extract_llm_decision)
        df['action'] = df.apply(
            lambda row: decide_final_action(row['llm_opinion'], row['llm_2_opinion']), axis=1
        )
        
        df = df.drop(columns=['llm_opinion', 'llm_2_opinion'])

    return df

def get_current_time_madrid():
    madrid_tz = pytz.timezone('Europe/Madrid')
    return datetime.now(madrid_tz).strftime("%Y-%m-%d %H:%M")

def normalize_for_tradingview(symbol, info):
    """
    If the JSON entry has a 'symbol' key (different from original), use it.
    Otherwise, use the original symbol.
    Remove any suffix like '.DE' when building the URL.
    """
    tv_symbol = info.get("symbol", symbol)
    return tv_symbol.split(".")[0]

def add_urls_column(buy_df, symbol_col="symbol"):
    """
    Adds a 'tradingview_url' column to the DataFrame.
    The URL is built based on the market and symbol info loaded from JSON.
    If symbol is not found, the value is 'NOT FOUND'.
    """

    # Load SYMBOLS_MARKETS from JSON
    project_root = Path(__file__).resolve().parent.parent
    json_path = project_root / "resources" / "symbols_markets.json"
    with open(json_path, "r", encoding="utf-8") as f:
        SYMBOLS_MARKETS = json.load(f)

    def build_url(symbol):
        if not isinstance(symbol, str):
            return "NOT FOUND"

        info = SYMBOLS_MARKETS.get(symbol)
        if not info or "market" not in info:
            return "NOT FOUND"

        tv_symbol = normalize_for_tradingview(symbol, info)
        market = info["market"]

        return f"https://en.tradingview.com/symbols/{market}-{tv_symbol}/technicals/"

    # Add the new column at the end
    buy_df["tradingview_url"] = buy_df[symbol_col].apply(build_url)
    return buy_df
