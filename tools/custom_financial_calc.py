
import pandas as pd
from datetime import datetime
import numpy as np
import logging
import yfinance as yf

from tools import technical_engine

logger = logging.getLogger(__name__)


def _compute_adx(df, period=14):
    """Compute ADX (Average Directional Index) and +DI / -DI."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    # When both are positive, keep only the larger
    plus_dm[(plus_dm > 0) & (minus_dm > 0) & (plus_dm <= minus_dm)] = 0
    minus_dm[(plus_dm > 0) & (minus_dm > 0) & (minus_dm < plus_dm)] = 0

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.ewm(alpha=1 / period, min_periods=period).mean()

    return adx, plus_di, minus_di


def _compute_stochastic_rsi(df, rsi_period=14, stoch_period=14, smooth_k=3, smooth_d=3):
    """Compute Stochastic RSI (%K and %D lines)."""
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / rsi_period, min_periods=rsi_period).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_period, min_periods=rsi_period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    rsi_min = rsi.rolling(stoch_period).min()
    rsi_max = rsi.rolling(stoch_period).max()
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-10)
    k_line = stoch_rsi.rolling(smooth_k).mean() * 100
    d_line = k_line.rolling(smooth_d).mean()

    return k_line, d_line


def _compute_obv(df):
    """Compute On-Balance Volume."""
    obv = pd.Series(0.0, index=df.index)
    obv.iloc[0] = df["volume"].iloc[0]
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] + df["volume"].iloc[i]
        elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] - df["volume"].iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i - 1]
    return obv


def _detect_bearish_divergence(df, lookback=14):
    """
    Detect bearish divergence: price makes a higher high while OBV or RSI makes a
    lower high. Treated as a RISK factor (not momentum). Returns True/False.
    """
    try:
        if len(df) < 2 * lookback:
            return False
        recent = df.tail(lookback)
        prior = df.iloc[-2 * lookback:-lookback]

        price_higher_high = recent["close"].max() > prior["close"].max()
        if not price_higher_high:
            return False

        obv_lower = False
        if "obv" in df.columns and recent["obv"].notna().any() and prior["obv"].notna().any():
            obv_lower = recent["obv"].max() < prior["obv"].max()

        rsi_lower = False
        if "rsi" in df.columns and recent["rsi"].notna().any() and prior["rsi"].notna().any():
            rsi_lower = recent["rsi"].max() < prior["rsi"].max()

        return bool(obv_lower or rsi_lower)
    except Exception as e:
        logger.warning(f"Divergence detection failed: {e}")
        return False


def _compute_fibonacci_levels(df, lookback=50):
    """Compute Fibonacci retracement levels from recent swing high/low."""
    recent = df.tail(lookback)
    swing_high = recent["high"].max()
    swing_low = recent["low"].min()
    diff = swing_high - swing_low

    return {
        "fib_0": swing_high,
        "fib_236": swing_high - 0.236 * diff,
        "fib_382": swing_high - 0.382 * diff,
        "fib_500": swing_high - 0.500 * diff,
        "fib_618": swing_high - 0.618 * diff,
        "fib_1": swing_low,
    }


def _detect_candlestick_patterns(df):
    """Detect basic candlestick patterns on the last few bars."""
    patterns = []
    if len(df) < 3:
        return patterns

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    body = latest["close"] - latest["open"]
    body_abs = abs(body)
    high_low_range = latest["high"] - latest["low"]
    if high_low_range == 0:
        return patterns

    upper_shadow = latest["high"] - max(latest["close"], latest["open"])
    lower_shadow = min(latest["close"], latest["open"]) - latest["low"]

    # Doji: very small body relative to range
    if body_abs < 0.1 * high_low_range:
        patterns.append("DOJI")

    # Hammer: small body at top, long lower shadow (bullish reversal)
    if lower_shadow > 2 * body_abs and upper_shadow < body_abs and body >= 0:
        patterns.append("HAMMER")

    # Inverted Hammer / Shooting Star
    if upper_shadow > 2 * body_abs and lower_shadow < body_abs:
        if body <= 0:
            patterns.append("SHOOTING_STAR")

    # Bullish Engulfing
    prev_body = prev["close"] - prev["open"]
    if prev_body < 0 and body > 0:
        if latest["open"] <= prev["close"] and latest["close"] >= prev["open"]:
            patterns.append("BULLISH_ENGULFING")

    # Bearish Engulfing
    if prev_body > 0 and body < 0:
        if latest["open"] >= prev["close"] and latest["close"] <= prev["open"]:
            patterns.append("BEARISH_ENGULFING")

    return patterns


def _compute_weekly_confirmation(df):
    """
    Resample daily data to weekly and compute key indicators for multi-timeframe confirmation.
    Returns a dict with weekly trend signals or None if insufficient data.
    """
    try:
        wdf = df.copy()
        wdf = wdf.set_index("date")
        weekly = wdf["close"].resample("W").last().dropna()
        if len(weekly) < 30:
            return None

        ma10w = weekly.rolling(10).mean()   # ~50 daily
        ma30w = weekly.rolling(30).mean()   # ~150 daily

        delta = weekly.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        rsi_w = 100 - (100 / (1 + rs))

        latest_close = weekly.iloc[-1]
        latest_ma10 = ma10w.iloc[-1]
        latest_ma30 = ma30w.iloc[-1]
        latest_rsi = rsi_w.iloc[-1]

        if pd.isna(latest_ma10) or pd.isna(latest_ma30) or pd.isna(latest_rsi):
            return None

        return {
            "weekly_trend_bullish": latest_ma10 > latest_ma30,
            "weekly_price_above_ma10": latest_close > latest_ma10,
            "weekly_rsi": latest_rsi,
            "weekly_ma10": float(latest_ma10),
            "weekly_ma30": float(latest_ma30),
        }
    except Exception as e:
        logger.warning(f"Weekly confirmation failed: {e}")
        return None


def _get_sp500_trend():
    """Fetch S&P500 recent data and determine market trend."""
    try:
        spy = yf.Ticker("^GSPC")
        data = spy.history(period="6mo")
        if data is None or data.empty or len(data) < 50:
            return None, 0.0

        data["ma50"] = data["Close"].rolling(50).mean()
        data["ma20"] = data["Close"].rolling(20).mean()
        latest = data.iloc[-1]

        price = latest["Close"]
        ma50 = latest["ma50"]
        ma20 = latest["ma20"]

        if pd.isna(ma50) or pd.isna(ma20):
            return None, 0.0

        # Score: positive = bullish market, negative = bearish
        score = 0.0
        if price > ma50:
            score += 1.0
        else:
            score -= 1.0
        if price > ma20:
            score += 0.5
        else:
            score -= 0.5
        if ma20 > ma50:
            score += 0.5
        else:
            score -= 0.5

        if score >= 1.0:
            trend = "BULLISH"
        elif score <= -1.0:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

        return trend, score
    except Exception as e:
        logger.warning(f"Could not fetch S&P500 data: {e}")
        return None, 0.0

def review_transactions(transactions_df: pd.DataFrame, hist_data: pd.DataFrame, revenue_percentage: float) -> pd.DataFrame:
    """
    Reviews open transactions and closes those that meet or exceed the required revenue percentage.

    Parameters:
        transactions_df (pd.DataFrame): DataFrame of transactions with columns like 'symbol', 'buy_date', 'buy_price', etc.
        hist_data (pd.DataFrame): DataFrame with symbols and current prices (columns: 'symbol', 'current_price').
        revenue_percentage (float): Minimum profit percentage to trigger a sale.

    Returns:
        pd.DataFrame: Rows of transactions that were updated (i.e., sold).
    """

    # Ensure date columns are parsed correctly
    transactions_df['buy_date'] = pd.to_datetime(transactions_df['buy_date'], errors='coerce')
    transactions_df['sell_date'] = pd.to_datetime(transactions_df['sell_date'], errors='coerce')

    updated_rows = []

    for _, row in hist_data.iterrows():
        symbol = row['symbol']
        try:
            current_price = float(row['current_price'])
        except ValueError:
            continue  # Skip rows with invalid price

        # Find the first open (unsold) transaction for the symbol
        open_tx = transactions_df[
            (transactions_df['symbol'] == symbol) & (transactions_df['sell_date'].isna())
        ]

        if open_tx.empty:
            continue

        idx = open_tx.index[0]

        buy_price = pd.to_numeric(transactions_df.at[idx, 'buy_price'], errors='coerce')
        if pd.isna(buy_price):
            continue

        # Calculate profit percentage
        percentage_benefit = ((current_price - buy_price) / buy_price) * 100

        if percentage_benefit < revenue_percentage:
            continue

        # Close the transaction (register sale)
        sell_date = datetime.today()
        transactions_df.loc[idx, 'sell_date'] = sell_date.strftime('%Y-%m-%d')
        transactions_df.loc[idx, 'sell_value'] = current_price
        transactions_df.loc[idx, 'buy_sell_days_diff'] = (sell_date - transactions_df.at[idx, 'buy_date']).days
        transactions_df.loc[idx, 'percentage_benefit'] = round(percentage_benefit, 2)

        updated_rows.append(transactions_df.loc[idx])

    return pd.DataFrame(updated_rows)


def evaluate_buy_interest(symbol: str, df: pd.DataFrame, current_price: float) -> dict:
    """
    Evaluates BUY, HOLD, or SELL interest for a stock based on technical indicators,
    historical volatility, monthly returns, breakouts, and momentum.
    Returns all numeric values as native Python floats rounded to 4 decimals.
    """

    logger.info(f"Evaluating buy interest for: {symbol}")
    try:
        df = df.copy()
        df.columns = df.columns.str.lower()
        df['date'] = pd.to_datetime(df['date'], utc=True)
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['open'] = pd.to_numeric(df['open'], errors='coerce')
        df['high'] = pd.to_numeric(df.get('high', df['close']), errors='coerce')
        df['low'] = pd.to_numeric(df.get('low', df['close']), errors='coerce')

        if len(df) < 200:
            raise ValueError("Insufficient data: at least 200 rows required.")

        # -------------------------
        # Technical Indicators
        # -------------------------
        df["ma50"] = df["close"].rolling(window=50).mean()
        df["ma200"] = df["close"].rolling(window=200).mean()

        # RSI (14 días)
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))
        df["rsi"] = df["rsi"].clip(lower=0, upper=100)

        # MACD
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["signal_line"] = df["macd"].ewm(span=9, adjust=False).mean()

        # MA50 Slope
        df["ma50_slope"] = df["ma50"].diff(5)

        # Short-term momentum: Rate of Change (ROC 10 días)
        df["roc_10"] = df["close"].pct_change(10)

        # Volatilidad histórica
        df["daily_return"] = df["close"].pct_change()
        df["volatility_20"] = df["daily_return"].rolling(20).std()
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        df["atr_14"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()

        # Breakout 20 días
        df["breakout_20"] = df["close"] > df["close"].rolling(20).max().shift(1)

        # Retorno mensual histórico
        df["monthly_return"] = df["close"].pct_change(21)
        monthly_10pct_prob = (df["monthly_return"] >= 0.10).mean()

        # EMA 20 for short-term trend
        df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()

        # MACD histogram trend (rising or falling over last 3 bars)
        df["macd_hist"] = df["macd"] - df["signal_line"]
        df["macd_hist_slope"] = df["macd_hist"].diff(3)

        # Bollinger Bands (20, 2)
        df["bb_mid"] = df["close"].rolling(20).mean()
        df["bb_std"] = df["close"].rolling(20).std()
        df["bb_upper"] = df["bb_mid"] + 2 * df["bb_std"]
        df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]

        # -------------------------
        # NEW: ADX (trend strength)
        # -------------------------
        adx_series, plus_di_series, minus_di_series = _compute_adx(df)
        df["adx"] = adx_series
        df["plus_di"] = plus_di_series
        df["minus_di"] = minus_di_series

        # -------------------------
        # NEW: Stochastic RSI
        # -------------------------
        stoch_k, stoch_d = _compute_stochastic_rsi(df)
        df["stoch_rsi_k"] = stoch_k
        df["stoch_rsi_d"] = stoch_d

        # -------------------------
        # NEW: OBV (On-Balance Volume)
        # -------------------------
        has_volume = "volume" in df.columns
        if has_volume:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
            df["vol_sma_20"] = df["volume"].rolling(20).mean()
            df["obv"] = _compute_obv(df)
            df["obv_sma_20"] = df["obv"].rolling(20).mean()

        # -------------------------
        # NEW: Fibonacci levels
        # -------------------------
        fib_levels = _compute_fibonacci_levels(df)

        # -------------------------
        # NEW: Candlestick patterns
        # -------------------------
        candle_patterns = _detect_candlestick_patterns(df)

        # -------------------------
        # NEW: Weekly timeframe confirmation
        # -------------------------
        weekly_conf = _compute_weekly_confirmation(df)

        # -------------------------
        # NEW: S&P500 market context
        # -------------------------
        market_trend, market_score = _get_sp500_trend()

        # -------------------------
        # Extract latest and previous
        # -------------------------
        latest = df.iloc[-1]
        previous = df.iloc[-2]

        # -------------------------
        # Collect raw indicator values
        # -------------------------
        signals_dict = {
            "SMA_50": latest["ma50"],
            "SMA_200": latest["ma200"],
            "RSI": latest["rsi"],
            "MACD": latest["macd"],
            "MACD_Signal": latest["signal_line"],
            "MACD_Hist": latest["macd"] - latest["signal_line"],
            "MA50_Slope": latest["ma50_slope"],
            "ROC_10": latest["roc_10"],
            "Volatility_20": latest["volatility_20"],
            "ATR_14": latest["atr_14"],
            "Breakout_20": latest["breakout_20"],
            "Monthly_10pct_Prob": monthly_10pct_prob,
            "Current_Price": current_price,
            "EMA_20": latest["ema_20"],
            "MACD_Hist_Slope": latest["macd_hist_slope"],
            "BB_Upper": latest["bb_upper"],
            "BB_Lower": latest["bb_lower"],
            "ADX": latest["adx"],
            "Plus_DI": latest["plus_di"],
            "Minus_DI": latest["minus_di"],
            "Stoch_RSI_K": latest["stoch_rsi_k"],
            "Stoch_RSI_D": latest["stoch_rsi_d"],
            "Fib_382": fib_levels["fib_382"],
            "Fib_500": fib_levels["fib_500"],
            "Fib_618": fib_levels["fib_618"],
            "Market_Trend": market_trend or "UNKNOWN",
        }
        if weekly_conf:
            signals_dict["Weekly_Trend_Bullish"] = weekly_conf["weekly_trend_bullish"]
            signals_dict["Weekly_Price_Above_MA10"] = weekly_conf["weekly_price_above_ma10"]
            signals_dict["Weekly_RSI"] = round(float(weekly_conf["weekly_rsi"]), 2)
            signals_dict["Weekly_MA10"] = round(weekly_conf["weekly_ma10"], 4)
            signals_dict["Weekly_MA30"] = round(weekly_conf["weekly_ma30"], 4)
        if has_volume:
            signals_dict["Volume"] = latest["volume"]
            signals_dict["Vol_SMA_20"] = latest["vol_sma_20"]
            signals_dict["OBV"] = latest["obv"]
            signals_dict["OBV_SMA_20"] = latest["obv_sma_20"]
        if candle_patterns:
            signals_dict["Candle_Patterns"] = ", ".join(candle_patterns)

        # -------------------------
        # NEW: bearish divergence (RISK factor, not momentum)
        # -------------------------
        bearish_divergence = _detect_bearish_divergence(df)

        # -------------------------
        # MACD fresh crossover detection (+1 bull / -1 bear / 0 none)
        # -------------------------
        macd_cross = 0
        if all(pd.notna([previous["macd"], previous["signal_line"], latest["macd"], latest["signal_line"]])):
            if previous["macd"] < previous["signal_line"] and latest["macd"] > latest["signal_line"]:
                macd_cross = 1
            elif previous["macd"] > previous["signal_line"] and latest["macd"] < latest["signal_line"]:
                macd_cross = -1

        # -------------------------
        # Build the common feature vector consumed by the layered engine.
        # All raw values; the engine normalizes each to a common scale.
        # -------------------------
        def _f(value, default=np.nan):
            return float(value) if pd.notna(value) else default

        features = {
            "price": current_price,
            # trend layer
            "sma50": _f(latest["ma50"]),
            "sma200": _f(latest["ma200"]),
            "ema20": _f(latest["ema_20"]),
            "ma50_slope": _f(latest["ma50_slope"]),
            "adx": _f(latest["adx"]),
            "plus_di": _f(latest["plus_di"]),
            "minus_di": _f(latest["minus_di"]),
            # momentum layer
            "rsi": _f(latest["rsi"]),
            "macd": _f(latest["macd"]),
            "macd_signal": _f(latest["signal_line"]),
            "macd_hist_slope": _f(latest["macd_hist_slope"]),
            "macd_cross": macd_cross,
            "stoch_rsi_k": _f(latest["stoch_rsi_k"]),
            "roc": _f(latest["roc_10"]),
            # risk layer
            "volatility": _f(latest["volatility_20"]),
            "bb_upper": _f(latest["bb_upper"]),
            "bearish_divergence": bool(bearish_divergence),
        }
        if has_volume:
            features["volume"] = _f(latest.get("volume"))
            features["vol_sma_20"] = _f(latest.get("vol_sma_20"))
            features["obv"] = _f(latest.get("obv"))
            features["obv_sma_20"] = _f(latest.get("obv_sma_20"))

        # Weekly (higher timeframe) confirmation feeds the TREND layer when available
        if weekly_conf:
            features["weekly_available"] = True
            features["weekly_trend_bullish"] = bool(weekly_conf["weekly_trend_bullish"])
            features["weekly_price_above_ma10"] = bool(weekly_conf["weekly_price_above_ma10"])
        else:
            features["weekly_available"] = False

        # -------------------------
        # Run the deterministic layered engine (sole decision maker)
        # -------------------------
        result = technical_engine.decide(features)
        decision = result["signal"]
        confidence = result["confidence"]

        # -------------------------
        # Convert NumPy types to native float and round
        # -------------------------
        signals_dict = {
            k: (round(float(v), 4) if isinstance(v, (np.generic, np.float64, np.int64)) else v)
            for k, v in signals_dict.items()
        }

        # Structured, deterministic technical output (no narrative)
        signals_dict["Regime"] = result["regime"]
        signals_dict["Strength"] = result["strength"]
        signals_dict["Trend_Score"] = result["sub_scores"]["trend_score"]
        signals_dict["Momentum_Score"] = result["sub_scores"]["momentum_score"]
        signals_dict["Risk_Score"] = result["sub_scores"]["risk_score"]
        signals_dict["Bearish_Divergence"] = bool(bearish_divergence)

        # Deterministic, structured factor breakdown (replaces narrative signals)
        active_signals = [
            f"signal={result['signal']}",
            f"strength={result['strength']}",
            f"regime={result['regime']}",
            f"trend_score={result['sub_scores']['trend_score']}",
            f"momentum_score={result['sub_scores']['momentum_score']}",
            f"risk_score={result['sub_scores']['risk_score']}",
        ]
        active_signals += [f"trend.{k}={v}" for k, v in result["factors"]["trend"].items()]
        active_signals += [f"momentum.{k}={v}" for k, v in result["factors"]["momentum"].items()]
        active_signals += [f"risk.{k}={v}" for k, v in result["factors"]["risk"].items()]

        logger.info(
            f"✅ Evaluated {symbol}: signal={decision}, strength={result['strength']}, "
            f"regime={result['regime']}, trend={result['sub_scores']['trend_score']}, "
            f"momentum={result['sub_scores']['momentum_score']}, risk={result['sub_scores']['risk_score']}, "
            f"confidence={confidence:.2f}"
        )

        return {
            "symbol": symbol,
            "evaluation": decision,
            "signal": decision,
            "strength": result["strength"],
            "regime": result["regime"],
            "confidence": round(confidence, 4),
            "sub_scores": result["sub_scores"],
            "factors": result["factors"],
            "active_signals": active_signals,
            "signals": signals_dict
        }

    except Exception as e:
        logger.error(f"❌ Evaluation failed for {symbol}: {e}")
        return {
            "symbol": symbol,
            "evaluation": "EVALUATION_FAILED",
            "confidence": 0.0,  # <--- agregado
            "active_signals": ["Evaluation failed due to error."],
            "signals": {"error": str(e)}
        }
