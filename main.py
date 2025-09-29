from dotenv import load_dotenv
import ast
import os
import pandas as pd
import logging
from tools import google_handler,finnhub_client,historicals,web_scrapper,custom_financial_calc as cfc,general,llms
from datetime import datetime
import numpy as np
import pytz  # o usa zoneinfo si estás en Python 3.9+

# Load .env file only if not running in production (e.g., GitHub Actions)
if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

def main():
    
    # Set up logging configuration
    log_level_str = os.getenv("LOG_LEVEL").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logging.basicConfig(level=log_level)
    logger = logging.getLogger(__name__)

    interest_symbol_list = ast.literal_eval(os.environ.get("SYMBOLS_INTEREST_LIST"))
    revenue_percentage =os.environ.get("REVENUE_PERCENTAGE")
    
    symbols_info_list = finnhub_client.get_symbols_info(interest_symbol_list)

    # by now we evaluate all the symbols, not just the losers
    #top_losers_data = finnhub_client.analyze_market_losers_from_interest_list(symbols_info_list)
    top_losers_data = symbols_info_list

    analysis_df = pd.DataFrame(top_losers_data)    

    for loser in top_losers_data:

        symbol=loser['symbol']
        current_price=loser['current_price']
        # get historical data        
        hist_data = historicals.get_historical_data(symbol)
        
        # get interest metrics
        metrics = cfc.evaluate_buy_interest(symbol,hist_data,current_price)

        # get trading view opinion
        td_opinion = web_scrapper.get_trading_view_opinion(symbol)

        # add opinions
        general.add_opinion(symbol,analysis_df,"manual_financial_analysis",metrics["evaluation"])
        general.add_opinion(symbol,analysis_df,"trading_view_opinion",td_opinion)

        if "failed" not in metrics["evaluation"]:
            general.add_opinion(symbol,analysis_df,"llm_opinion",llms.get_llm_signals_analysis( metrics["signals"],symbol,current_price))
        else:
            general.add_opinion(symbol,analysis_df,"llm_opinion","error: metrics not provided")
    
    # generate and filter by decision column where is BUY
    analysis_df = general.generate_decision_column(analysis_df, os.environ.get("FORCE_OPINION"))
    buy_df = analysis_df[analysis_df['decision'] == 'BUY']   

    # update transaction log
    transactions_file_id = os.environ.get("GDRIVE_FILE_ID")

    update_df = pd.DataFrame(symbols_info_list)

    transactions_df = google_handler.load_data(transactions_file_id)    
    trans_updated_df = google_handler.update_transactions(update_df,transactions_df, revenue_percentage)

    final_df = pd.concat([trans_updated_df, buy_df], ignore_index=True)\
                    .sort_values(by='buy_date', ascending=False).head(365)
    
    google_handler.save_dataframe_file_id(final_df,transactions_file_id)

    # get Madrid time
    madrid_tz = pytz.timezone('Europe/Madrid')
    now_madrid = datetime.now(madrid_tz)

    buy_df['recommendation_date'] = now_madrid

    # if dataframe is empty we create at least 1 row to control that the process is being executed
    if buy_df.empty:
        empty_row = {col: (now_madrid if col == 'recommendation_date' else np.nan) for col in buy_df.columns}
        empty_df = pd.DataFrame([empty_row])
        buy_df = pd.concat([buy_df, empty_df], ignore_index=True)


    buy_file_id = os.environ.get("BUY_RECOMMENDATIONS_ID")
    google_handler.save_dataframe_file_id(buy_df,buy_file_id)

    anlysis_file_id = os.environ.get("ANALYSIS_FILE_ID")
    google_handler.save_dataframe_file_id(analysis_df,anlysis_file_id)

    
if __name__ == "__main__":
    main()
