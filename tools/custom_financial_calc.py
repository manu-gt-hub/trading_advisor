
import pandas as pd
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger(__name__)

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


import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

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
        df['date'] = pd.to_datetime(df['date'])
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
        # Evaluate signals
        # -------------------------
        active_signals = []
        buy_signals = 0
        sell_signals = 0

        # MA Crossover
        if pd.notna(latest["ma50"]) and pd.notna(latest["ma200"]):
            if latest["ma50"] > latest["ma200"]:
                active_signals.append("✅ Bullish trend (MA50 > MA200)")
                buy_signals += 1
            else:
                active_signals.append("❌ Bearish trend (MA50 < MA200)")
                sell_signals += 1

        # RSI
        if pd.notna(latest["rsi"]):
            rsi = latest["rsi"]
            if 40 < rsi < 70:
                active_signals.append(f"✅ RSI in healthy range ({rsi:.2f})")
                buy_signals += 1
            elif rsi < 30:
                active_signals.append(f"✅ RSI oversold ({rsi:.2f})")
                buy_signals += 1
            elif rsi > 70:
                active_signals.append(f"❌ RSI overbought ({rsi:.2f})")
                sell_signals += 1
            else:
                active_signals.append(f"⚠️ RSI neutral ({rsi:.2f})")

        # MACD Crossover
        if all(pd.notna([previous["macd"], previous["signal_line"], latest["macd"], latest["signal_line"]])):
            if previous["macd"] < previous["signal_line"] and latest["macd"] > latest["signal_line"]:
                active_signals.append("✅ MACD bullish crossover")
                buy_signals += 1
            elif previous["macd"] > previous["signal_line"] and latest["macd"] < latest["signal_line"]:
                active_signals.append("❌ MACD bearish crossover")
                sell_signals += 1

        # MA50 slope
        if pd.notna(latest["ma50_slope"]):
            if latest["ma50_slope"] > 0:
                active_signals.append("📈 Positive MA50 slope (uptrend momentum)")
                buy_signals += 0.5
            elif latest["ma50_slope"] < 0:
                active_signals.append("📉 Negative MA50 slope (downtrend momentum)")
                sell_signals += 0.5

        # ROC_10 momentum
        if pd.notna(latest["roc_10"]):
            if latest["roc_10"] > 0:
                active_signals.append(f"📈 Positive 10-day ROC ({latest['roc_10']:.2%})")
                buy_signals += 0.5
            else:
                active_signals.append(f"📉 Negative 10-day ROC ({latest['roc_10']:.2%})")
                sell_signals += 0.5

        # Breakout
        if latest["breakout_20"]:
            active_signals.append("🚀 20-day breakout")
            buy_signals += 1

        # Monthly 10% probability
        if monthly_10pct_prob >= 0.15:
            active_signals.append(f"📊 Historical monthly +10% probability: {monthly_10pct_prob:.1%}")
            buy_signals += 1
        else:
            active_signals.append(f"⚠️ Low historical monthly +10% probability: {monthly_10pct_prob:.1%}")
            sell_signals += 0.5

        # -------------------------
        # Final decision
        # -------------------------
        if buy_signals > sell_signals:
            decision = "BUY"
        elif sell_signals > buy_signals:
            decision = "SELL"
        else:
            decision = "HOLD"

        # Confidence score
        confidence = (buy_signals - sell_signals) / max(buy_signals + sell_signals, 1)

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
            "active_signals": ["Evaluation failed due to error."],
            "signals": {"error": str(e)}
        }
