from dotenv import load_dotenv
import ast
import argparse
import os
import pandas as pd
import logging
from tools import google_handler, finnhub_client, historicals, custom_financial_calc as cfc, general, llms, news_sentiment
from tools.risk_management import compute_stop_loss_take_profit, filter_correlated_buys


TRANSACTION_COLUMNS = ['symbol', 'buy_value', 'buy_date', 'stop_loss', 'take_profit', 'risk_reward_ratio', 'tradingview_url']
TRANSACTION_COLUMN_ORDER = [
    'symbol', 'buy_value', 'buy_date', 'sell_value', 'sell_date',
    'buy_sell_days_diff', 'percentage_benefit', 'stop_loss', 'take_profit',
    'highest_price', 'risk_reward_ratio', 'tradingview_url',
]


def load_config():
    """Load environment variables and set up logging."""
    if not os.getenv("GITHUB_ACTIONS"):
        load_dotenv()

    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logging.basicConfig(level=log_level)
    general.install_secret_redaction()
    logger = logging.getLogger(__name__)

    return {
        "logger": logger,
        "symbols_interest_list": ast.literal_eval(os.environ.get("SYMBOLS_INTEREST_LIST", "[]")),
        "revenue_percentage": float(os.environ.get("REVENUE_PERCENTAGE", 0)) if os.environ.get("REVENUE_PERCENTAGE") else None,
        "max_records": int(os.environ.get("TRANSACTIONS_MAX_RECORDS", 100)),
        "transactions_file_id": os.environ.get("GDRIVE_FILE_ID"),
        "buy_file_id": os.environ.get("BUY_RECOMMENDATIONS_ID"),
        "analysis_file_id": os.environ.get("ANALYSIS_FILE_ID"),
        "force_opinion": os.environ.get("FORCE_OPINION"),
        "min_buy_confidence": float(os.environ.get("MIN_BUY_CONFIDENCE", 0.6)),
        "min_risk_reward_ratio": float(os.environ.get("MIN_RISK_REWARD_RATIO", 1.2)),
        "news_sent_analysis": os.environ.get("NEWS_SENT_ANALYSIS", "false").lower() == "true",
    }

def analyze_symbol(symbol_data, sp500_override=None):
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

        metrics = cfc.evaluate_buy_interest(symbol, hist_data, current_price, sp500_override=sp500_override)

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
    # The technical engine is the SOLE decider. The LLM is optionally invoked
    # when the technical signal is BUY, only to AUDIT it (adjust confidence /
    # flag incoherence). It never re-classifies the signal.
    # Set LLM_AUDIT_ENABLED=false to skip the LLM entirely (faster, cheaper).
    llm_audit_enabled = os.environ.get("LLM_AUDIT_ENABLED", "true").lower() == "true"
    rev_pct_str = os.environ.get('REVENUE_PERCENTAGE')
    rev_pct = float(rev_pct_str) if rev_pct_str else None

    for item in analysis:
        symbol = item["symbol"]
        try:
            metrics = item["metrics"]
            evaluation = metrics["evaluation"]
            confidence = metrics.get("confidence", 0.0)

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
            elif "FAILED" not in evaluation.upper():
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
            sl_tp = compute_stop_loss_take_profit(item['current_price'], sigs.get('ATR_14'), revenue_percentage=rev_pct)
            df.loc[df['symbol'] == symbol, 'stop_loss'] = sl_tp['stop_loss']
            df.loc[df['symbol'] == symbol, 'take_profit'] = sl_tp['take_profit']
            df.loc[df['symbol'] == symbol, 'risk_reward_ratio'] = sl_tp['risk_reward_ratio']
        except Exception as e:
            logger.error(f"❌ Error enriching {symbol}: {e}. Skipping.")

    return general.generate_action_column(df, force_opinion)

def build_transactions_log(trans_updated_df, buy_df, max_records):
    """
    Merge reviewed transactions with today's buys into the log saved to Drive.
    Newest first, capped at max_records — but open positions are always kept,
    otherwise a position older than the cap would vanish and never be closed.
    """
    buy_for_tx = buy_df[[c for c in TRANSACTION_COLUMNS if c in buy_df.columns]].copy()
    frames = [f for f in (trans_updated_df, buy_for_tx) if not f.empty]
    final_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=TRANSACTION_COLUMNS)

    # Normalize buy_date to strings before sorting to avoid
    # TypeError when transactions have datetime64 and buy_df has strings
    if 'buy_date' in final_df.columns:
        final_df['buy_date'] = final_df['buy_date'].astype(str).replace('NaT', '')
        sort_key = pd.to_datetime(final_df['buy_date'], errors='coerce', format='mixed')
        final_df = final_df.assign(_sort=sort_key).sort_values(
            by=['_sort', 'buy_date'], ascending=False, na_position='last', kind='stable'
        ).drop(columns='_sort')

    if 'sell_value' in final_df.columns:
        is_open = pd.to_numeric(final_df['sell_value'], errors='coerce').isna()
    else:
        is_open = pd.Series(True, index=final_df.index)
    keep = final_df.index[:max_records].union(final_df.index[is_open])
    final_df = final_df.loc[final_df.index.isin(keep)]

    # Enforce consistent column order so sell columns appear right after buy columns
    ordered_cols = [c for c in TRANSACTION_COLUMN_ORDER if c in final_df.columns]
    extra_cols = [c for c in final_df.columns if c not in TRANSACTION_COLUMN_ORDER]
    return final_df[ordered_cols + extra_cols]

def update_and_save_transactions(config, analysis_df, buy_df, transactions_df=None):
    logger = logging.getLogger(__name__)
    try:
        if transactions_df is None:
            transactions_df = google_handler.load_data(config["transactions_file_id"])
        if transactions_df is None:
            logger.error("❌ Could not load transactions from Google Drive. Skipping transaction update.")
            return

        trans_updated_df = google_handler.update_transactions(
            pd.DataFrame(analysis_df), transactions_df, config["revenue_percentage"]
        )
        final_df = build_transactions_log(trans_updated_df, buy_df, config["max_records"])

        logger.info(f"📝 Saving {len(final_df)} transactions (including {len(buy_df)} new buys)")
        google_handler.save_dataframe_file_id(final_df, config["transactions_file_id"])
    except Exception as e:
        logger.error(f"❌ Failed to update/save transactions: {e}", exc_info=True)

def filter_buys_by_confidence(analysis_df, min_confidence):
    """Filter BUY actions by minimum confidence threshold."""
    buy_df = analysis_df[
        (analysis_df['action'] == 'BUY') &
        (analysis_df['technical_confidence'] >= min_confidence)
    ].copy()
    return buy_df


def filter_buys_by_risk_reward(buy_df, min_rr=1.2):
    """Filter out BUY recommendations with bad risk/reward ratio."""
    if buy_df.empty or 'risk_reward_ratio' not in buy_df.columns:
        return buy_df
    bad_rr = buy_df[buy_df['risk_reward_ratio'].apply(
        lambda x: pd.notna(x) and x < min_rr
    )]
    return buy_df[~buy_df.index.isin(bad_rr.index)].copy()


def _apply_filter(name, buy_df, kept_df, analysis_df, reason_fn, logger):
    """Record filter_status for the BUYs a filter removed and log the survivors."""
    for _, row in buy_df[~buy_df.index.isin(kept_df.index)].iterrows():
        reason = reason_fn(row)
        analysis_df.loc[analysis_df['symbol'] == row['symbol'], 'filter_status'] = reason
        logger.info(f"🚫 {name} filter: {row['symbol']} — {reason}")
    logger.info(f"📊 After {name} filter: {list(kept_df['symbol'])}")
    return kept_df


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

def _is_market_day(today=None):
    """Check if today is a US stock market trading day (NYSE calendar)."""
    return general.is_us_market_day(today)

def main(show_dataframes=False):

    config = load_config()
    logger = config["logger"]
    now_madrid = general.get_current_time_madrid()

    if not _is_market_day():
        logger.info("📅 Market closed today (weekend or holiday). Skipping execution.")
        return

    symbols_info_list = finnhub_client.get_symbols_info(config["symbols_interest_list"])
    # Normalize symbols (e.g., BHE.DE -> BHE) so they match across pipeline
    for item in symbols_info_list:
        item["symbol"] = item["symbol"].split(".")[0]
    analysis_df = pd.DataFrame(symbols_info_list)

    # S&P500 context is the same for every symbol: fetch it once per run
    sp500 = cfc._get_sp500_trend()
    analysis_results = [r for r in (analyze_symbol(data, sp500) for data in symbols_info_list) if r is not None]

    # Enrich analysis_df with opinions
    analysis_df = enrich_analysis_df(analysis_df, analysis_results, config["force_opinion"])

    # Ensure news columns always exist in the saved output, even when there are no
    # BUY candidates (the news filter below only populates them for BUY rows).
    analysis_df['news_sentiment'] = "Not evaluated (no BUY candidate)"
    analysis_df['earnings_soon'] = False
    analysis_df['filter_status'] = ''

    # Filter to only BUY recommendations with sufficient confidence
    min_conf = config["min_buy_confidence"]
    all_buys = analysis_df[analysis_df['action'] == 'BUY'].copy()
    logger.info(f"📊 Stocks with action=BUY: {list(all_buys['symbol'])} ({len(all_buys)} total)")
    buy_df = _apply_filter(
        "Confidence", all_buys, filter_buys_by_confidence(all_buys, min_conf), analysis_df,
        lambda r: f"🚫 confidence {r['technical_confidence']:.2f} < {min_conf}", logger,
    )

    # Transactions are loaded once: used by the position filter and the exit review
    transactions_df = None
    try:
        transactions_df = google_handler.load_data(config["transactions_file_id"])
    except Exception as e:
        logger.warning(f"⚠️ Could not load transactions: {e}")

    # Position tracking: skip BUY if already holding an open position
    if not buy_df.empty:
        try:
            if transactions_df is not None and not transactions_df.empty:
                # Handle blank strings from Google Sheets: coerce sell_value to numeric
                sell_values = pd.to_numeric(transactions_df['sell_value'], errors='coerce')
                open_positions = transactions_df[sell_values.isna()]['symbol'].tolist()
                buy_df = _apply_filter(
                    "Position", buy_df, buy_df[~buy_df['symbol'].isin(open_positions)], analysis_df,
                    lambda r: "🚫 already holding open position", logger,
                )
        except Exception as e:
            logger.warning(f"⚠️ Position tracking check failed: {e}. Continuing without filter.")

    # Risk/Reward filter: block BUYs with bad risk/reward ratio
    if not buy_df.empty and 'risk_reward_ratio' in buy_df.columns:
        min_rr = config["min_risk_reward_ratio"]
        buy_df = _apply_filter(
            "R:R", buy_df, filter_buys_by_risk_reward(buy_df, min_rr), analysis_df,
            lambda r: f"🚫 R:R {r['risk_reward_ratio']:.2f} < {min_rr}", logger,
        )

    # News sentiment filter: block BUYs with upcoming earnings or strongly negative news
    if not buy_df.empty:
        blocked = {}
        for _, row in buy_df.iterrows():
            try:
                news_result = news_sentiment.evaluate_news_filter(
                    row['symbol'],
                    news_sentiment_enabled=config["news_sent_analysis"]
                )
                # Write sentiment back to analysis_df so it appears in Google Drive
                mask = analysis_df['symbol'] == row['symbol']
                analysis_df.loc[mask, 'news_sentiment'] = news_result['news_sentiment']['summary']
                analysis_df.loc[mask, 'earnings_soon'] = news_result['earnings_soon']
                if news_result['block_buy']:
                    blocked[row['symbol']] = news_result['reason']
            except Exception as e:
                logger.error(f"❌ News filter failed for {row['symbol']}: {e}. Keeping BUY.")
        buy_df = _apply_filter(
            "News", buy_df, buy_df[~buy_df['symbol'].isin(blocked)], analysis_df,
            lambda r: f"🚫 news: {blocked[r['symbol']]}", logger,
        )

    buy_df = buy_df.rename(columns={'current_price': 'buy_value'})
    buy_df['buy_date'] = now_madrid
    buy_date_col = buy_df.pop('buy_date')
    buy_df.insert(2, 'buy_date', buy_date_col)

    buy_df = general.add_urls_column(buy_df)

    # Diversification filter: remove highly correlated BUYs
    if len(buy_df) >= 2:
        buy_df = _apply_filter(
            "Correlation", buy_df, filter_correlated_buys(buy_df), analysis_df,
            lambda r: '🚫 correlated with another BUY', logger,
        )

    # Mark surviving BUYs as passed
    for sym in set(buy_df['symbol']):
        analysis_df.loc[analysis_df['symbol'] == sym, 'filter_status'] = '✅ passed all filters'

    logger.info(f"📊 Final BUY list: {list(buy_df['symbol'])} ({len(buy_df)} stocks)")

    # Update and save all outputs
    update_and_save_transactions(config, analysis_df, buy_df, transactions_df)
    save_outputs(buy_df, analysis_df, config)

    logger.info("✅ successfully run main")
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
