
import pandas as pd
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger(__name__)

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

        # -------------------------
        # Short-term momentum: Rate of Change (ROC 10 días)
        # -------------------------
        df["roc_10"] = df["close"].pct_change(10)

        # -------------------------
        # Volatilidad histórica
        # -------------------------
        df["daily_return"] = df["close"].pct_change()
        df["volatility_20"] = df["daily_return"].rolling(20).std()
        df["atr_14"] = (df["close"] - df["open"]).abs().rolling(14).mean()  # aproximación ATR

        # -------------------------
        # Breakout 20 días
        # -------------------------
        df["breakout_20"] = df["close"] > df["close"].rolling(20).max().shift(1)

        # -------------------------
        # Retorno mensual histórico
        # -------------------------
        df["monthly_return"] = df["close"].pct_change(21)
        monthly_10pct_prob = (df["monthly_return"] >= 0.10).mean()  # probabilidad histórica >10%/mes

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
            "Current_Price": current_price
        }

        # -------------------------
        # Additional indicators for improved precision
        # -------------------------
        # EMA 20 for short-term trend
        df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()

        # MACD histogram trend (rising or falling over last 3 bars)
        df["macd_hist"] = df["macd"] - df["signal_line"]
        df["macd_hist_slope"] = df["macd_hist"].diff(3)

        # Volume confirmation (if available)
        has_volume = "volume" in df.columns and pd.notna(latest.get("volume", None))
        if has_volume:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
            df["vol_sma_20"] = df["volume"].rolling(20).mean()

        # Bollinger Bands (20, 2)
        df["bb_mid"] = df["close"].rolling(20).mean()
        df["bb_std"] = df["close"].rolling(20).std()
        df["bb_upper"] = df["bb_mid"] + 2 * df["bb_std"]
        df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]

        # Refresh latest/previous with new columns
        latest = df.iloc[-1]
        previous = df.iloc[-2]

        # Add new signals to dict
        signals_dict["EMA_20"] = latest["ema_20"]
        signals_dict["MACD_Hist_Slope"] = latest["macd_hist_slope"]
        signals_dict["BB_Upper"] = latest["bb_upper"]
        signals_dict["BB_Lower"] = latest["bb_lower"]
        if has_volume:
            signals_dict["Volume"] = latest["volume"]
            signals_dict["Vol_SMA_20"] = latest["vol_sma_20"]

        # -------------------------
        # Weighted signal evaluation
        # -------------------------
        # Weights reflect importance for short-term (1-4 week) setups
        active_signals = []
        buy_score = 0.0
        sell_score = 0.0

        # --- TREND (high weight: 2.0) ---
        # MA50/MA200 crossover — primary trend direction
        if pd.notna(latest["ma50"]) and pd.notna(latest["ma200"]):
            if latest["ma50"] > latest["ma200"]:
                active_signals.append("✅ Bullish trend (MA50 > MA200)")
                buy_score += 2.0
            else:
                active_signals.append("❌ Bearish trend (MA50 < MA200)")
                sell_score += 2.0

        # Price position relative to key moving averages (weight: 1.5)
        if pd.notna(latest["ma50"]) and pd.notna(latest["ema_20"]):
            above_ema20 = current_price > latest["ema_20"]
            above_ma50 = current_price > latest["ma50"]
            if above_ema20 and above_ma50:
                active_signals.append(f"✅ Price above EMA20 ({latest['ema_20']:.2f}) and MA50 ({latest['ma50']:.2f})")
                buy_score += 1.5
            elif not above_ema20 and not above_ma50:
                active_signals.append(f"❌ Price below EMA20 ({latest['ema_20']:.2f}) and MA50 ({latest['ma50']:.2f})")
                sell_score += 1.5
            else:
                active_signals.append(f"⚠️ Price between EMA20 and MA50 (mixed)")

        # --- MOMENTUM (weight: 1.5) ---
        # RSI with nuanced scoring
        if pd.notna(latest["rsi"]):
            rsi = latest["rsi"]
            if rsi < 30:
                active_signals.append(f"✅ RSI oversold — reversal opportunity ({rsi:.2f})")
                buy_score += 1.5
            elif 30 <= rsi < 45:
                active_signals.append(f"⚠️ RSI weak ({rsi:.2f})")
                sell_score += 0.5
            elif 45 <= rsi < 55:
                active_signals.append(f"⚠️ RSI neutral ({rsi:.2f})")
            elif 55 <= rsi <= 70:
                active_signals.append(f"✅ RSI strong bullish ({rsi:.2f})")
                buy_score += 1.5
            else:  # > 70
                active_signals.append(f"❌ RSI overbought ({rsi:.2f})")
                sell_score += 1.5

        # MACD crossover (weight: 1.5)
        if all(pd.notna([previous["macd"], previous["signal_line"], latest["macd"], latest["signal_line"]])):
            if previous["macd"] < previous["signal_line"] and latest["macd"] > latest["signal_line"]:
                active_signals.append("✅ MACD bullish crossover")
                buy_score += 1.5
            elif previous["macd"] > previous["signal_line"] and latest["macd"] < latest["signal_line"]:
                active_signals.append("❌ MACD bearish crossover")
                sell_score += 1.5

        # MACD histogram momentum — rising/falling trend (weight: 1.0)
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

        # --- SHORT-TERM MOMENTUM (weight: 1.0) ---
        # MA50 slope
        if pd.notna(latest["ma50_slope"]):
            if latest["ma50_slope"] > 0:
                active_signals.append("📈 Positive MA50 slope (uptrend momentum)")
                buy_score += 0.75
            elif latest["ma50_slope"] < 0:
                active_signals.append("📉 Negative MA50 slope (downtrend momentum)")
                sell_score += 0.75

        # ROC_10 momentum (weight: 1.0)
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

        # --- BREAKOUT & PATTERN (weight: 1.0) ---
        if latest["breakout_20"]:
            active_signals.append("🚀 20-day breakout")
            buy_score += 1.0
            # Confirm breakout with volume if available
            if has_volume and pd.notna(latest.get("vol_sma_20")):
                if latest["volume"] > 1.5 * latest["vol_sma_20"]:
                    active_signals.append("🚀 Breakout confirmed by high volume")
                    buy_score += 0.5

        # Bollinger Band position (weight: 0.75)
        if pd.notna(latest["bb_lower"]) and pd.notna(latest["bb_upper"]):
            if current_price <= latest["bb_lower"]:
                active_signals.append(f"✅ Price at lower Bollinger Band — potential bounce ({latest['bb_lower']:.2f})")
                buy_score += 0.75
            elif current_price >= latest["bb_upper"]:
                active_signals.append(f"❌ Price at upper Bollinger Band — potential pullback ({latest['bb_upper']:.2f})")
                sell_score += 0.75

        # --- VOLATILITY FILTER (weight: 0.5) ---
        # High volatility increases risk — penalize both sides slightly
        if pd.notna(latest["volatility_20"]):
            vol = latest["volatility_20"]
            if vol > 0.04:
                active_signals.append(f"⚠️ High volatility ({vol:.4f}) — elevated risk")
                # Reduce conviction: add to the weaker side
                sell_score += 0.5
            elif vol < 0.015:
                active_signals.append(f"⚠️ Very low volatility ({vol:.4f}) — potential breakout ahead")

        # --- HISTORICAL PROBABILITY (weight: 0.5) ---
        if monthly_10pct_prob >= 0.15:
            active_signals.append(f"📊 Historical monthly +10% probability: {monthly_10pct_prob:.1%}")
            buy_score += 0.5
        else:
            active_signals.append(f"⚠️ Low historical monthly +10% probability: {monthly_10pct_prob:.1%}")
            sell_score += 0.25

        # -------------------------
        # Final decision with threshold
        # -------------------------
        net_score = buy_score - sell_score
        total_score = buy_score + sell_score

        # Require a minimum margin to avoid weak signals
        if total_score == 0:
            decision = "HOLD"
        elif net_score >= 2.0:
            decision = "BUY"
        elif net_score <= -2.0:
            decision = "SELL"
        else:
            decision = "HOLD"

        # Confidence score normalized to [-1, 1]
        confidence = net_score / max(total_score, 1)

        # -------------------------
        # Convert NumPy types to native float and round
        # -------------------------
        signals_dict = {
            k: (round(float(v), 4) if isinstance(v, (np.generic, np.float64, np.int64)) else v)
            for k, v in signals_dict.items()
        }

        logger.info(f"✅ Successfully evaluated buy interest for {symbol}: {signals_dict}")

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
