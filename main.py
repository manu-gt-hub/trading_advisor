from dotenv import load_dotenv
import ast
import argparse
import os
import pandas as pd
import logging
from datetime import datetime
from tools import google_handler, finnhub_client, historicals, custom_financial_calc as cfc, general, llms, news_sentiment
from tools.risk_management import compute_stop_loss_take_profit, filter_correlated_buys
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
        "min_buy_confidence": float(os.environ.get("MIN_BUY_CONFIDENCE", 0.6)),
        "news_sent_analysis": os.environ.get("NEWS_SENT_ANALYSIS", "false").lower() == "true",
    }

def analyze_symbol(symbol_data):
    """Analyze a single stock symbol. Returns None if analysis fails."""
    symbol = symbol_data['symbol']
    current_price = symbol_data['current_price']
    #normalize symbol in cases like: RHM.DE
    symbol = symbol.split(".")[0]

    try:
        hist_data = historicals.get_historical_data(symbol)
        if hist_data is None or hist_data.empty:
            logging.getLogger(__name__).warning(f"⚠️ No historical data for {symbol}. Skipping.")
            return None

        metrics = cfc.evaluate_buy_interest(symbol, hist_data, current_price)

        return {
            "symbol": symbol,
            "current_price": current_price,
            "metrics": metrics,
        }
    except Exception as e:
        logging.getLogger(__name__).error(f"❌ Analysis failed for {symbol}: {e}. Skipping.")
        return None

def enrich_analysis_df(df, analysis, force_opinion):
    """Add analysis opinions to the DataFrame."""
    logger = logging.getLogger(__name__)

    for item in analysis:
        symbol = item["symbol"]
        try:
            metrics = item["metrics"]
            evaluation = metrics["evaluation"]
            confidence = metrics.get("confidence", 0.0)

            # The technical engine is the SOLE decider. The LLM is optionally invoked
            # when the technical signal is BUY, only to AUDIT it (adjust confidence /
            # flag incoherence). It never re-classifies the signal.
            # Set LLM_AUDIT_ENABLED=false to skip the LLM entirely (faster, cheaper).
            llm_audit_enabled = os.environ.get("LLM_AUDIT_ENABLED", "true").lower() == "true"
            
            if evaluation == "BUY" and llm_audit_enabled:
                technical_result = {
                    "regime": metrics.get("regime"),
                    "strength": metrics.get("strength"),
                    "sub_scores": metrics.get("sub_scores", {}),
                }
                audit = llms.audit_buy_signal(
                    metrics["signals"], symbol, item["current_price"], technical_result
                )
                # Apply the bounded confidence adjustment from the auditor
                confidence = max(-1.0, min(1.0, confidence + audit["adjustment"]))
                coherence = "COHERENT" if audit["coherent"] else "INCOHERENT"
                llm_opinion = f"{coherence} | adj={audit['adjustment']:+.2f} | {audit['reason']}"
                df.loc[df['symbol'] == symbol, 'llm_confidence'] = round(audit["adjustment"], 4)
            elif evaluation == "BUY" and not llm_audit_enabled:
                llm_opinion = "BUY - LLM audit disabled (technical decides)"
                df.loc[df['symbol'] == symbol, 'llm_confidence'] = 0.0
            elif "failed" not in evaluation:
                llm_opinion = f"{evaluation} - LLM not called (technical decides)"
                df.loc[df['symbol'] == symbol, 'llm_confidence'] = 0.0
            else:
                llm_opinion = "error: metrics not provided"
                df.loc[df['symbol'] == symbol, 'llm_confidence'] = 0.0

            general.add_opinion(symbol, df, "llm_opinion", llm_opinion)

            # Structured, deterministic technical label (signal + regime + sub-scores)
            sigs = metrics['signals']
            indicator_parts = []
            for key in ['RSI', 'MACD', 'ADX', 'SMA_50', 'SMA_200', 'ATR_14', 'Volatility_20', 'ROC_10', 'Stoch_RSI_K', 'Market_Trend']:
                if key in sigs and sigs[key] is not None:
                    val = sigs[key]
                    indicator_parts.append(f"{key}={round(val, 2) if isinstance(val, float) else val}")
            indicators_str = ', '.join(indicator_parts)
            sub = metrics.get("sub_scores", {})
            structured = (
                f"regime={metrics.get('regime', 'UNKNOWN')}, "
                f"strength={metrics.get('strength', 'UNKNOWN')}, "
                f"trend={sub.get('trend_score')}, momentum={sub.get('momentum_score')}, "
                f"risk={sub.get('risk_score')}"
            )
            custom_label = f"{confidence:.2f} {evaluation} | {structured} | {indicators_str}"
            general.add_opinion(symbol, df, "manual_financial_analysis", custom_label)

            # Store numeric (audited) confidence for filtering
            df.loc[df['symbol'] == symbol, 'technical_confidence'] = confidence

            # Store decision reason (explains why not BUY, or confirms BUY)
            df.loc[df['symbol'] == symbol, 'decision_reason'] = metrics.get('decision_reason', '')

            # Compute stop-loss and take-profit levels
            atr = metrics['signals'].get('ATR_14')
            sl_tp = compute_stop_loss_take_profit(item['current_price'], atr, revenue_percentage=os.environ.get('REVENUE_PERCENTAGE'))
            df.loc[df['symbol'] == symbol, 'stop_loss'] = sl_tp['stop_loss']
            df.loc[df['symbol'] == symbol, 'take_profit'] = sl_tp['take_profit']
            df.loc[df['symbol'] == symbol, 'risk_reward_ratio'] = sl_tp['risk_reward_ratio']
        except Exception as e:
            logger.error(f"❌ Error enriching {symbol}: {e}. Skipping.")

    return general.generate_action_column(df, force_opinion)

def update_and_save_transactions(config, analysis_df, buy_df, now_madrid):
    logger = logging.getLogger(__name__)
    try:
        transactions_df = google_handler.load_data(config["transactions_file_id"])
        if transactions_df is None:
            logger.error("❌ Could not load transactions from Google Drive. Skipping transaction update.")
            return

        update_df = pd.DataFrame(analysis_df)

        trans_updated_df = google_handler.update_transactions(update_df, transactions_df, config["revenue_percentage"])

        final_df = pd.concat([trans_updated_df, buy_df], ignore_index=True)\
                     .sort_values(by='buy_date', ascending=False).head(config["max_records"])

        google_handler.save_dataframe_file_id(final_df, config["transactions_file_id"])
    except Exception as e:
        logger.error(f"❌ Failed to update/save transactions: {e}")

def save_outputs(buy_df, analysis_df, config):
    logger = logging.getLogger(__name__)
    try:
        google_handler.save_dataframe_file_id(buy_df, config["buy_file_id"])
    except Exception as e:
        logger.error(f"❌ Failed to save buy recommendations: {e}")
    try:
        google_handler.save_dataframe_file_id(analysis_df, config["analysis_file_id"])
    except Exception as e:
        logger.error(f"❌ Failed to save analysis: {e}")

def _is_market_day():
    """Check if today is a US stock market trading day (Mon-Fri, not major holidays)."""
    from datetime import date as date_cls
    today = date_cls.today()
    # Weekend check
    if today.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False
    # US market holidays (fixed dates — doesn't cover floating holidays like Thanksgiving)
    us_holidays = [
        (1, 1),   # New Year's Day
        (7, 4),   # Independence Day
        (12, 25), # Christmas Day
    ]
    if (today.month, today.day) in us_holidays:
        return False
    return True

def main(show_dataframes=False):

    config = load_config()
    now_madrid = general.get_current_time_madrid()

    if not _is_market_day():
        config["logger"].info("📅 Market closed today (weekend or holiday). Skipping execution.")
        return

    symbols_info_list = finnhub_client.get_symbols_info(config["symbols_interest_list"])
    # Normalize symbols (e.g., BHE.DE -> BHE) so they match across pipeline
    for item in symbols_info_list:
        item["symbol"] = item["symbol"].split(".")[0]
    analysis_df = pd.DataFrame(symbols_info_list)

    # Analyze each symbol and collect analysis results (skip failures)
    analysis_results = [r for r in (analyze_symbol(data) for data in symbols_info_list) if r is not None]

    # Enrich analysis_df with opinions
    analysis_df = enrich_analysis_df(analysis_df, analysis_results, config["force_opinion"])

    # Ensure news columns always exist in the saved output, even when there are no
    # BUY candidates (the news filter below only populates them for BUY rows).
    analysis_df['news_sentiment'] = "Not evaluated (no BUY candidate)"
    analysis_df['earnings_soon'] = False

    # Filter to only BUY recommendations with sufficient confidence
    min_conf = config["min_buy_confidence"]
    buy_df = analysis_df[
        (analysis_df['action'] == 'BUY') &
        (analysis_df['technical_confidence'] >= min_conf)
    ].copy()

    # Log filtered-out low-confidence BUYs
    low_conf_buys = analysis_df[
        (analysis_df['action'] == 'BUY') &
        (analysis_df['technical_confidence'] < min_conf)
    ]
    for _, row in low_conf_buys.iterrows():
        config['logger'].info(
            f"Filtered out BUY for {row['symbol']}: confidence {row['technical_confidence']:.2f} < {min_conf}"
        )

    # Position tracking: skip BUY if already holding an open position
    if not buy_df.empty:
        try:
            transactions_df = google_handler.load_data(config["transactions_file_id"])
            if transactions_df is not None and not transactions_df.empty:
                open_positions = transactions_df[
                    transactions_df['sell_value'].isna()
                ]['symbol'].tolist()
                already_held = buy_df[buy_df['symbol'].isin(open_positions)]
                for _, row in already_held.iterrows():
                    config['logger'].info(
                        f"🚫 Position filter: skipping BUY for {row['symbol']} — already holding open position"
                    )
                buy_df = buy_df[~buy_df['symbol'].isin(open_positions)].copy()
        except Exception as e:
            config['logger'].warning(f"⚠️ Position tracking check failed: {e}. Continuing without filter.")

    # Risk/Reward filter: block BUYs with bad risk/reward ratio
    if not buy_df.empty and 'risk_reward_ratio' in buy_df.columns:
        min_rr = 1.2
        bad_rr = buy_df[buy_df['risk_reward_ratio'].apply(
            lambda x: pd.notna(x) and x < min_rr
        )]
        for _, row in bad_rr.iterrows():
            config['logger'].info(
                f"🚫 R:R filter blocked BUY for {row['symbol']}: "
                f"ratio {row['risk_reward_ratio']:.2f} < {min_rr}"
            )
        buy_df = buy_df[~buy_df.index.isin(bad_rr.index)].copy()

    # News sentiment filter: block BUYs with upcoming earnings or strongly negative news
    if not buy_df.empty:
        blocked_symbols = []
        for _, row in buy_df.iterrows():
            try:
                news_result = news_sentiment.evaluate_news_filter(
                    row['symbol'],
                    news_sentiment_enabled=config["news_sent_analysis"]
                )
                # Write sentiment back to analysis_df so it appears in Google Drive
                analysis_df.loc[analysis_df['symbol'] == row['symbol'], 'news_sentiment'] = (
                    news_result['news_sentiment']['summary']
                )
                analysis_df.loc[analysis_df['symbol'] == row['symbol'], 'earnings_soon'] = (
                    news_result['earnings_soon']
                )
                if news_result['block_buy']:
                    blocked_symbols.append(row['symbol'])
                    config['logger'].info(
                        f"🚫 News filter blocked BUY for {row['symbol']}: {news_result['reason']}"
                    )
            except Exception as e:
                config['logger'].error(f"❌ News filter failed for {row['symbol']}: {e}. Keeping BUY.")

        if blocked_symbols:
            buy_df = buy_df[~buy_df['symbol'].isin(blocked_symbols)].copy()
    buy_df = buy_df.rename(columns={'current_price': 'buy_value'})
    buy_df['buy_date'] = datetime.today().strftime('%Y-%m-%d')
    buy_date_col = buy_df.pop('buy_date')
    buy_df.insert(2, 'buy_date', buy_date_col)

    buy_df = general.add_urls_column(buy_df)

    # Diversification filter: remove highly correlated BUYs
    if len(buy_df) >= 2:
        buy_df = filter_correlated_buys(buy_df, max_correlation=0.75)

    # Update and save all outputs
    update_and_save_transactions(config, analysis_df, buy_df, now_madrid)
    save_outputs(buy_df, analysis_df, config)

    config.get("logger").info("✅ successfully run main")
    if show_dataframes:
        print("\n--- DataFrame Analysis ---")
        print(analysis_df)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="execute main script")
    parser.add_argument(
        "--test",
        action="store_true",
        help="show final DFs for testing/debug"
    )
    args = parser.parse_args()
    main(show_dataframes=args.test)