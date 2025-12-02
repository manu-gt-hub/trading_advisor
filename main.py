from dotenv import load_dotenv
import ast
import os
import pandas as pd
import logging
from tools import google_handler, finnhub_client, historicals, web_scrapper, custom_financial_calc as cfc, general, llms
import numpy as np


def load_config():
    """Load environment variables and set up logging."""
    if not os.getenv("GITHUB_ACTIONS"):
        load_dotenv()
    
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    logging.basicConfig(level=log_level)
    logger = logging.getLogger(__name__)
    
    return {
        "logger": logger,
        "symbols_interest_list": ast.literal_eval(os.environ.get("SYMBOLS_INTEREST_LIST", "[]")),
        "revenue_percentage": os.environ.get("REVENUE_PERCENTAGE"),
        "max_records": int(os.environ.get("TRANSACTIONS_MAX_RECORDS", 100)),
        "transactions_file_id": os.environ.get("GDRIVE_FILE_ID"),
        "buy_file_id": os.environ.get("BUY_RECOMMENDATIONS_ID"),
        "analysis_file_id": os.environ.get("ANALYSIS_FILE_ID"),
        "force_opinion": os.environ.get("FORCE_OPINION"),
    }

def analyze_symbol(symbol_data):
    """Analyze a single stock symbol."""
    symbol = symbol_data['symbol']
    current_price = symbol_data['current_price']

    hist_data = historicals.get_historical_data(symbol)
    metrics = cfc.evaluate_buy_interest(symbol, hist_data, current_price)
    # tv_opinion = web_scrapper.get_trading_view_opinion(symbol)
    # investing_opinion = web_scrapper.get_investing_opinion(symbol)

    return {
        "symbol": symbol,
        "current_price": current_price,
        "metrics": metrics,
    }

def enrich_analysis_df(df, analysis, force_opinion):
    """Add analysis opinions to the DataFrame."""
    for item in analysis:
        symbol = item["symbol"]
        metrics = item["metrics"]
        # tv_opinion = item["tv_opinion"]
        # investing_opinion = item["investing_opinion"]

        # TODO: enhance manual calculations
        #general.add_opinion(symbol, df, "manual_financial_analysis", metrics["evaluation"])
 
        #general.add_opinion(symbol, df, "trading_view_opinion", tv_opinion)
        #general.add_opinion(symbol, df, "investing_opinion", investing_opinion)

        if "failed" not in metrics["evaluation"]:
            llm_opinion = llms.get_gpt_signals_analysis(metrics["signals"], symbol, item["current_price"])
        else:
            llm_opinion = "error: metrics not provided"

        general.add_opinion(symbol, df, "llm_opinion", llm_opinion)

    return general.generate_action_column(df, force_opinion)

def update_and_save_transactions(config, analysis_df, buy_df, now_madrid):
    transactions_df = google_handler.load_data(config["transactions_file_id"])
    update_df = pd.DataFrame(analysis_df)

    trans_updated_df = google_handler.update_transactions(update_df, transactions_df, config["revenue_percentage"])

    final_df = pd.concat([trans_updated_df, buy_df], ignore_index=True)\
                 .sort_values(by='buy_date', ascending=False).head(config["max_records"])

    google_handler.save_dataframe_file_id(final_df, config["transactions_file_id"])

def save_outputs(buy_df, analysis_df, config):
    google_handler.save_dataframe_file_id(buy_df, config["buy_file_id"])
    google_handler.save_dataframe_file_id(analysis_df, config["analysis_file_id"])

def main():
    config = load_config()
    now_madrid = general.get_current_time_madrid()

    symbols_info_list = finnhub_client.get_symbols_info(config["symbols_interest_list"])
    analysis_df = pd.DataFrame(symbols_info_list)

    # Analyze each symbol and collect analysis results
    analysis_results = [analyze_symbol(data) for data in symbols_info_list]

    # Enrich analysis_df with opinions
    analysis_df = enrich_analysis_df(analysis_df, analysis_results, config["force_opinion"])

    # Filter to only BUY recommendations
    buy_df = analysis_df[analysis_df['action'] == 'BUY'].copy()
    buy_df['buy_date'] = now_madrid
    buy_df = buy_df.rename(columns={'current_price': 'buy_value'})
    buy_date_col = buy_df.pop('buy_date')
    buy_df.insert(2, 'buy_date', buy_date_col)

    # Update and save all outputs
    update_and_save_transactions(config, symbols_info_list, buy_df, now_madrid)
    save_outputs(buy_df, analysis_df, config)

if __name__ == "__main__":
    main()
