
import pandas as pd
from datetime import datetime
import numpy as np
import logging
import yfinance as yf

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
        # Determine ADX regime for dynamic weights
        # -------------------------
        adx_value = latest["adx"] if pd.notna(latest["adx"]) else 20
        strong_trend = adx_value >= 25
        # In strong trends, trend signals matter more; in ranging markets, mean-reversion matters more
        trend_multiplier = 1.3 if strong_trend else 0.7
        reversion_multiplier = 0.7 if strong_trend else 1.3

        # -------------------------
        # Weighted signal evaluation
        # -------------------------
        active_signals = []
        buy_score = 0.0
        sell_score = 0.0

        # --- ADX TREND STRENGTH ---
        if pd.notna(latest["adx"]):
            if strong_trend:
                active_signals.append(f"📊 Strong trend detected (ADX={adx_value:.1f})")
                if pd.notna(latest["plus_di"]) and pd.notna(latest["minus_di"]):
                    if latest["plus_di"] > latest["minus_di"]:
                        active_signals.append(f"✅ Bullish directional (+DI > -DI)")
                        buy_score += 1.0
                    else:
                        active_signals.append(f"❌ Bearish directional (-DI > +DI)")
                        sell_score += 1.0
            else:
                active_signals.append(f"📊 Weak/ranging market (ADX={adx_value:.1f})")

        # --- TREND (dynamic weight) ---
        if pd.notna(latest["ma50"]) and pd.notna(latest["ma200"]):
            if latest["ma50"] > latest["ma200"]:
                active_signals.append("✅ Bullish trend (MA50 > MA200)")
                buy_score += 2.0 * trend_multiplier
            else:
                active_signals.append("❌ Bearish trend (MA50 < MA200)")
                sell_score += 2.0 * trend_multiplier

        # Price position relative to key moving averages (dynamic weight)
        if pd.notna(latest["ma50"]) and pd.notna(latest["ema_20"]):
            above_ema20 = current_price > latest["ema_20"]
            above_ma50 = current_price > latest["ma50"]
            if above_ema20 and above_ma50:
                active_signals.append(f"✅ Price above EMA20 ({latest['ema_20']:.2f}) and MA50 ({latest['ma50']:.2f})")
                buy_score += 1.5 * trend_multiplier
            elif not above_ema20 and not above_ma50:
                active_signals.append(f"❌ Price below EMA20 ({latest['ema_20']:.2f}) and MA50 ({latest['ma50']:.2f})")
                sell_score += 1.5 * trend_multiplier
            else:
                active_signals.append(f"⚠️ Price between EMA20 and MA50 (mixed)")

        # --- MOMENTUM: RSI ---
        if pd.notna(latest["rsi"]):
            rsi = latest["rsi"]
            if rsi < 30:
                active_signals.append(f"✅ RSI oversold — reversal opportunity ({rsi:.2f})")
                buy_score += 1.5 * reversion_multiplier
            elif 30 <= rsi < 45:
                active_signals.append(f"⚠️ RSI weak ({rsi:.2f})")
                sell_score += 0.5
            elif 45 <= rsi < 55:
                active_signals.append(f"⚠️ RSI neutral ({rsi:.2f})")
            elif 55 <= rsi <= 70:
                active_signals.append(f"✅ RSI strong bullish ({rsi:.2f})")
                buy_score += 1.5 * trend_multiplier
            else:
                active_signals.append(f"❌ RSI overbought ({rsi:.2f})")
                sell_score += 1.5 * reversion_multiplier

        # --- MOMENTUM: Stochastic RSI ---
        if pd.notna(latest["stoch_rsi_k"]) and pd.notna(latest["stoch_rsi_d"]):
            stk = latest["stoch_rsi_k"]
            std = latest["stoch_rsi_d"]
            if stk < 20 and std < 20:
                active_signals.append(f"✅ Stochastic RSI oversold (K={stk:.1f}, D={std:.1f})")
                buy_score += 1.0 * reversion_multiplier
            elif stk > 80 and std > 80:
                active_signals.append(f"❌ Stochastic RSI overbought (K={stk:.1f}, D={std:.1f})")
                sell_score += 1.0 * reversion_multiplier
            # Bullish crossover: K crosses above D in oversold zone
            if stk > std and previous["stoch_rsi_k"] <= previous["stoch_rsi_d"] and stk < 50:
                active_signals.append(f"✅ Stochastic RSI bullish crossover")
                buy_score += 0.75
            # Bearish crossover: K crosses below D in overbought zone
            elif stk < std and previous["stoch_rsi_k"] >= previous["stoch_rsi_d"] and stk > 50:
                active_signals.append(f"❌ Stochastic RSI bearish crossover")
                sell_score += 0.75

        # --- MACD crossover ---
        if all(pd.notna([previous["macd"], previous["signal_line"], latest["macd"], latest["signal_line"]])):
            if previous["macd"] < previous["signal_line"] and latest["macd"] > latest["signal_line"]:
                active_signals.append("✅ MACD bullish crossover")
                buy_score += 1.5
            elif previous["macd"] > previous["signal_line"] and latest["macd"] < latest["signal_line"]:
                active_signals.append("❌ MACD bearish crossover")
                sell_score += 1.5

        # MACD histogram momentum
        if pd.notna(latest["macd_hist_slope"]):
            if latest["macd_hist_slope"] > 0 and latest["macd_hist"] > 0:
                active_signals.append(f"✅ MACD histogram rising in positive territory")
                buy_score += 1.0
            elif latest["macd_hist_slope"] > 0 and latest["macd_hist"] <= 0:
                active_signals.append(f"📈 MACD histogram recovering (still negative)")
                buy_score += 0.5
            elif latest["macd_hist_slope"] < 0 and latest["macd_hist"] < 0:
                active_signals.append(f"❌ MACD histogram falling in negative territory")
                sell_score += 1.0
            elif latest["macd_hist_slope"] < 0 and latest["macd_hist"] >= 0:
                active_signals.append(f"📉 MACD histogram weakening (still positive)")
                sell_score += 0.5

        # --- SHORT-TERM MOMENTUM ---
        if pd.notna(latest["ma50_slope"]):
            if latest["ma50_slope"] > 0:
                active_signals.append("📈 Positive MA50 slope (uptrend momentum)")
                buy_score += 0.75
            elif latest["ma50_slope"] < 0:
                active_signals.append("📉 Negative MA50 slope (downtrend momentum)")
                sell_score += 0.75

        # ROC_10 momentum
        if pd.notna(latest["roc_10"]):
            roc = latest["roc_10"]
            if roc > 0.05:
                active_signals.append(f"✅ Strong positive 10-day ROC ({roc:.2%})")
                buy_score += 1.0
            elif roc > 0:
                active_signals.append(f"📈 Mild positive 10-day ROC ({roc:.2%})")
                buy_score += 0.5
            elif roc > -0.05:
                active_signals.append(f"📉 Mild negative 10-day ROC ({roc:.2%})")
                sell_score += 0.5
            else:
                active_signals.append(f"❌ Strong negative 10-day ROC ({roc:.2%})")
                sell_score += 1.0

        # --- BREAKOUT & VOLUME ---
        if latest["breakout_20"]:
            active_signals.append("🚀 20-day breakout")
            buy_score += 1.0
            if has_volume and pd.notna(latest.get("vol_sma_20")):
                if latest["volume"] > 1.5 * latest["vol_sma_20"]:
                    active_signals.append("🚀 Breakout confirmed by high volume")
                    buy_score += 0.5

        # --- OBV (On-Balance Volume) ---
        if has_volume and pd.notna(latest.get("obv")) and pd.notna(latest.get("obv_sma_20")):
            obv = latest["obv"]
            obv_sma = latest["obv_sma_20"]
            if obv > obv_sma:
                active_signals.append(f"✅ OBV above 20-day average — accumulation (institutional buying)")
                buy_score += 1.0
            elif obv < obv_sma:
                active_signals.append(f"❌ OBV below 20-day average — distribution (institutional selling)")
                sell_score += 1.0

        # --- BOLLINGER BANDS (dynamic weight based on ADX) ---
        if pd.notna(latest["bb_lower"]) and pd.notna(latest["bb_upper"]):
            if current_price <= latest["bb_lower"]:
                active_signals.append(f"✅ Price at lower Bollinger Band — potential bounce ({latest['bb_lower']:.2f})")
                buy_score += 0.75 * reversion_multiplier
            elif current_price >= latest["bb_upper"]:
                active_signals.append(f"❌ Price at upper Bollinger Band — potential pullback ({latest['bb_upper']:.2f})")
                sell_score += 0.75 * reversion_multiplier

        # --- FIBONACCI LEVELS ---
        fib_382 = fib_levels["fib_382"]
        fib_500 = fib_levels["fib_500"]
        fib_618 = fib_levels["fib_618"]
        # Price near key Fibonacci support → potential bounce
        for level_name, level_val in [("38.2%", fib_382), ("50%", fib_500), ("61.8%", fib_618)]:
            if abs(current_price - level_val) / level_val < 0.02:  # within 2% of level
                active_signals.append(f"📐 Price near Fibonacci {level_name} level ({level_val:.2f})")
                # If price is at support in bullish context, it's a buy signal
                if pd.notna(latest["ma50"]) and current_price > latest["ma50"]:
                    buy_score += 0.5
                else:
                    sell_score += 0.5
                break  # only count nearest level

        # --- CANDLESTICK PATTERNS ---
        bullish_candles = {"HAMMER", "BULLISH_ENGULFING"}
        bearish_candles = {"SHOOTING_STAR", "BEARISH_ENGULFING"}
        for p in candle_patterns:
            if p in bullish_candles:
                active_signals.append(f"🕯️ Bullish candle pattern: {p}")
                buy_score += 0.75
            elif p in bearish_candles:
                active_signals.append(f"🕯️ Bearish candle pattern: {p}")
                sell_score += 0.75
            elif p == "DOJI":
                active_signals.append(f"🕯️ Doji — indecision candle")

        # --- VOLATILITY FILTER ---
        if pd.notna(latest["volatility_20"]):
            vol = latest["volatility_20"]
            if vol > 0.04:
                active_signals.append(f"⚠️ High volatility ({vol:.4f}) — elevated risk")
                sell_score += 0.5
            elif vol < 0.015:
                active_signals.append(f"⚠️ Very low volatility ({vol:.4f}) — potential breakout ahead")

        # --- HISTORICAL PROBABILITY ---
        if monthly_10pct_prob >= 0.15:
            active_signals.append(f"📊 Historical monthly +10% probability: {monthly_10pct_prob:.1%}")
            buy_score += 0.5
        else:
            active_signals.append(f"⚠️ Low historical monthly +10% probability: {monthly_10pct_prob:.1%}")
            sell_score += 0.25

        # --- WEEKLY TIMEFRAME CONFIRMATION ---
        if weekly_conf:
            w_trend = weekly_conf["weekly_trend_bullish"]
            w_above = weekly_conf["weekly_price_above_ma10"]
            w_rsi = weekly_conf["weekly_rsi"]

            if w_trend and w_above:
                active_signals.append(f"✅ Weekly trend BULLISH (MA10w > MA30w, price above MA10w)")
                buy_score += 1.5
            elif not w_trend and not w_above:
                active_signals.append(f"❌ Weekly trend BEARISH (MA10w < MA30w, price below MA10w)")
                sell_score += 1.5
            else:
                active_signals.append(f"⚠️ Weekly trend mixed (trend={'up' if w_trend else 'down'}, price={'above' if w_above else 'below'} MA10w)")

            if w_rsi < 30:
                active_signals.append(f"✅ Weekly RSI oversold ({w_rsi:.1f})")
                buy_score += 0.5
            elif w_rsi > 70:
                active_signals.append(f"❌ Weekly RSI overbought ({w_rsi:.1f})")
                sell_score += 0.5

        # --- MARKET CONTEXT (S&P500) ---
        if market_trend:
            if market_trend == "BULLISH":
                active_signals.append(f"🌍 Market context: S&P500 BULLISH (score={market_score:.1f})")
                buy_score += 1.0
            elif market_trend == "BEARISH":
                active_signals.append(f"🌍 Market context: S&P500 BEARISH (score={market_score:.1f})")
                sell_score += 1.0
                # Penalize BUYs in bearish market
                buy_score *= 0.8
            else:
                active_signals.append(f"🌍 Market context: S&P500 NEUTRAL (score={market_score:.1f})")

        # -------------------------
        # Signal diversity: count how many categories agree
        # Categories: trend, momentum, volume, structure (fib/candles), market context
        # -------------------------
        category_scores = {
            "trend": 0.0,      # MA50/200, EMA20, MA50 slope, ADX direction, weekly trend
            "momentum": 0.0,   # RSI, StochRSI, MACD, ROC, MACD hist
            "volume": 0.0,     # OBV, breakout volume, breakout
            "structure": 0.0,  # Bollinger, Fibonacci, candles
            "context": 0.0,    # Market trend, weekly RSI, historical prob, volatility
        }
        # Re-tally scores by category from the signals already computed
        # Trend signals
        if pd.notna(latest["ma50"]) and pd.notna(latest["ma200"]):
            category_scores["trend"] += 1 if latest["ma50"] > latest["ma200"] else -1
        if pd.notna(latest["ma50"]) and pd.notna(latest["ema_20"]):
            if current_price > latest["ema_20"] and current_price > latest["ma50"]:
                category_scores["trend"] += 1
            elif current_price < latest["ema_20"] and current_price < latest["ma50"]:
                category_scores["trend"] -= 1
        if pd.notna(latest["ma50_slope"]):
            category_scores["trend"] += 1 if latest["ma50_slope"] > 0 else -1
        if pd.notna(latest["adx"]) and strong_trend and pd.notna(latest["plus_di"]) and pd.notna(latest["minus_di"]):
            category_scores["trend"] += 1 if latest["plus_di"] > latest["minus_di"] else -1
        if weekly_conf and weekly_conf["weekly_trend_bullish"] and weekly_conf["weekly_price_above_ma10"]:
            category_scores["trend"] += 1
        elif weekly_conf and not weekly_conf["weekly_trend_bullish"] and not weekly_conf["weekly_price_above_ma10"]:
            category_scores["trend"] -= 1

        # Momentum signals
        if pd.notna(latest["rsi"]):
            if latest["rsi"] < 30 or (55 <= latest["rsi"] <= 70):
                category_scores["momentum"] += 1
            elif latest["rsi"] > 70 or (30 <= latest["rsi"] < 45):
                category_scores["momentum"] -= 1
        if pd.notna(latest["stoch_rsi_k"]) and pd.notna(latest["stoch_rsi_d"]):
            if latest["stoch_rsi_k"] < 20:
                category_scores["momentum"] += 1
            elif latest["stoch_rsi_k"] > 80:
                category_scores["momentum"] -= 1
        if pd.notna(latest["macd"]) and pd.notna(latest["signal_line"]):
            category_scores["momentum"] += 1 if latest["macd"] > latest["signal_line"] else -1
        if pd.notna(latest["roc_10"]):
            category_scores["momentum"] += 1 if latest["roc_10"] > 0 else -1

        # Volume signals
        if has_volume and pd.notna(latest.get("obv")) and pd.notna(latest.get("obv_sma_20")):
            category_scores["volume"] += 1 if latest["obv"] > latest["obv_sma_20"] else -1
        if latest["breakout_20"]:
            category_scores["volume"] += 1

        # Structure signals (Bollinger, Fib, candles)
        if pd.notna(latest["bb_lower"]) and current_price <= latest["bb_lower"]:
            category_scores["structure"] += 1
        elif pd.notna(latest["bb_upper"]) and current_price >= latest["bb_upper"]:
            category_scores["structure"] -= 1
        for p in candle_patterns:
            if p in {"HAMMER", "BULLISH_ENGULFING"}:
                category_scores["structure"] += 1
            elif p in {"SHOOTING_STAR", "BEARISH_ENGULFING"}:
                category_scores["structure"] -= 1

        # Context
        if market_trend == "BULLISH":
            category_scores["context"] += 1
        elif market_trend == "BEARISH":
            category_scores["context"] -= 1

        # Count how many categories agree with the net direction
        net_score = buy_score - sell_score
        net_direction = 1 if net_score > 0 else (-1 if net_score < 0 else 0)
        categories_agreeing = sum(
            1 for v in category_scores.values()
            if (v > 0 and net_direction > 0) or (v < 0 and net_direction < 0)
        )
        categories_with_signal = sum(1 for v in category_scores.values() if v != 0)
        diversity_ratio = categories_agreeing / max(categories_with_signal, 1)

        # -------------------------
        # Final decision with threshold
        # -------------------------
        total_score = buy_score + sell_score

        # MA200 gate: price must be above MA200 for BUY (trend confirmation)
        below_ma200 = False
        if pd.notna(latest["ma200"]) and current_price < latest["ma200"]:
            below_ma200 = True

        if total_score == 0:
            decision = "HOLD"
        elif net_score >= 2.5 and not below_ma200:
            decision = "BUY"
        elif net_score >= 2.5 and below_ma200:
            decision = "HOLD"
            active_signals.append(f"⛔ BUY blocked: price ({current_price:.2f}) below MA200 ({latest['ma200']:.2f})")
        elif net_score <= -2.5:
            decision = "SELL"
        else:
            decision = "HOLD"

        # Confidence score normalized to [-1, 1], penalized by low diversity
        raw_confidence = net_score / max(total_score, 1)
        # If less than 3 categories agree, reduce confidence (signal is concentrated)
        diversity_penalty = 1.0 if categories_agreeing >= 3 else (0.85 if categories_agreeing == 2 else 0.7)
        confidence = raw_confidence * diversity_penalty

        # -------------------------
        # Convert NumPy types to native float and round
        # -------------------------
        signals_dict = {
            k: (round(float(v), 4) if isinstance(v, (np.generic, np.float64, np.int64)) else v)
            for k, v in signals_dict.items()
        }

        signals_dict["Signal_Diversity"] = f"{categories_agreeing}/{categories_with_signal} categories"
        signals_dict["Diversity_Penalty"] = round(diversity_penalty, 2)

        logger.info(f"✅ Successfully evaluated buy interest for {symbol}: decision={decision}, confidence={confidence:.2f}, diversity={categories_agreeing}/{categories_with_signal}, buy={buy_score:.1f}, sell={sell_score:.1f}")

        return {
            "symbol": symbol,
            "evaluation": decision,
            "confidence": round(confidence, 2),
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
