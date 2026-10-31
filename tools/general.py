import pandas as pd
import logging
from datetime import date, datetime, timedelta
import pytz
import os
import json
from pathlib import Path

logger = logging.getLogger(__name__)

SECRET_ENV_VARS = ("FINNHUB_API_KEY", "OPENAI_API_KEY", "ALPHA_API_KEY", "GDRIVE_CREDENTIALS_JSON")


def ssl_verify():
    """TLS verification for outbound HTTP: on unless DISABLE_SSL_VERIFY is set."""
    return os.getenv("DISABLE_SSL_VERIFY", "").lower() not in ("1", "true", "yes")


class SecretRedactingFilter(logging.Filter):
    """Mask API keys in log records (e.g. URLs echoed by requests' HTTPError)."""

    def filter(self, record):
        secrets = [v for v in (os.environ.get(k) for k in SECRET_ENV_VARS) if v and len(v) >= 8]
        if secrets:
            msg = record.getMessage()
            for secret in secrets:
                msg = msg.replace(secret, "***")
            record.msg, record.args = msg, ()
        return True


def install_secret_redaction():
    """Attach SecretRedactingFilter to every root handler (idempotent)."""
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, SecretRedactingFilter) for f in handler.filters):
            handler.addFilter(SecretRedactingFilter())


def _observed(d):
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year, month, weekday):
    d = date(year, month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def nyse_holidays(year):
    """Full-day NYSE closures for a year (regular rules, no ad-hoc closures)."""
    holidays = {
        _nth_weekday(year, 1, 0, 3),            # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),            # Presidents' Day
        _easter(year) - timedelta(days=2),      # Good Friday
        _last_weekday(year, 5, 0),              # Memorial Day
        _observed(date(year, 7, 4)),            # Independence Day
        _nth_weekday(year, 9, 0, 1),            # Labor Day
        _nth_weekday(year, 11, 3, 4),           # Thanksgiving
        _observed(date(year, 12, 25)),          # Christmas
    }
    # New Year's Day: a Saturday holiday is NOT moved to Friday Dec 31
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:
        holidays.add(_observed(new_year))
    if year >= 2022:
        holidays.add(_observed(date(year, 6, 19)))  # Juneteenth
    return holidays


def is_us_market_day(day=None):
    """True on NYSE trading days. Defaults to today's date in New York."""
    if day is None:
        day = datetime.now(pytz.timezone("America/New_York")).date()
    return day.weekday() < 5 and day not in nyse_holidays(day.year)


def add_opinion(symbol,df,new_column_name,opinion):
    df.loc[df['symbol'] == symbol, new_column_name] = opinion

def extract_custom_decision(opinion):
    if not isinstance(opinion, str):
        return None
    return opinion.split(' ')[1].strip().upper()  # Returns 'SELL', 'BUY', etc.


def apply_audit_veto(technical_decision, llm_opinion):
    """
    The technical engine is the SOLE decider. The LLM is an AUDITOR, not a second
    decision system: it can ONLY downgrade a technical BUY to HOLD when it flags the
    setup INCOHERENT. It can never create, upgrade, or flip a signal on its own.

    Parameters:
        technical_decision (str): The deterministic technical signal ('BUY'/'SELL'/'HOLD').
        llm_opinion (str): The auditor output, e.g. 'INCOHERENT | adj=-0.30 | reason'.

    Returns:
        str: The final action after applying the (BUY-only) incoherence veto.
    """
    if technical_decision == 'BUY' and isinstance(llm_opinion, str) and 'INCOHERENT' in llm_opinion.upper():
        logger.info("Audit veto: technical BUY downgraded to HOLD — LLM flagged INCOHERENT")
        return 'HOLD'
    return technical_decision

def generate_action_column(df: pd.DataFrame, opinion_type: str) -> pd.DataFrame:
    """
    Adds an 'action' column to the DataFrame.

    Parameters:
        df (pd.DataFrame): DataFrame with 'manual_financial_analysis' and 'llm_opinion' columns.
        opinion_type (str): "CUSTOM" = technical label only (ignores the LLM audit veto);
            anything else = DEFAULT (technical decides, LLM INCOHERENT downgrades BUY to HOLD).
            The legacy "LLM1"/"LLM2" modes relied on LLMs that no longer emit decisions and
            fall back to DEFAULT.

    Returns:
        pd.DataFrame: Original DataFrame with 'action' column added.
    """
    opinion_type = (opinion_type or "").strip().upper()
    logger.debug(f"Opinion type: {opinion_type}")

    if opinion_type in ("LLM1", "LLM2"):
        logger.warning(f"FORCE_OPINION={opinion_type} is no longer supported; using DEFAULT.")

    if opinion_type == "CUSTOM":
        logger.debug("set decision logic as CUSTOM (technical analysis only)")
        df['action'] = df['manual_financial_analysis'].apply(extract_custom_decision)
        return df

    logger.debug("set decision logic as DEFAULT (technical decides, LLM audits)")
    df['action'] = df['manual_financial_analysis'].apply(extract_custom_decision)
    if 'llm_opinion' in df.columns:
        df['action'] = df.apply(
            lambda row: apply_audit_veto(row['action'], row['llm_opinion']),
            axis=1
        )
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
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            SYMBOLS_MARKETS = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"❌ Could not load symbols_markets.json: {e}")
        buy_df["tradingview_url"] = "NOT FOUND"
        return buy_df

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
