
import pandas as pd
from datetime import datetime

def review_transactions(path: str, df: pd.DataFrame, revenue_percentage: float) -> pd.DataFrame:
    """
    Reviews active transactions and closes those that meet the required revenue percentage.

    Parameters:
        path (str): CSV file path containing transactions
        df (pd.DataFrame): DataFrame with updated symbol and current_price
        revenue_percentage (float): Minimum profit percentage to trigger a sale

    Returns:
        pd.DataFrame: Rows that were updated (sold)
    """
    # Load existing transactions from CSV
    transactions_df = pd.read_csv(path)

    # Ensure buy/sell dates are datetime
    transactions_df['buy_date'] = pd.to_datetime(transactions_df['buy_date'], errors='coerce')
    transactions_df['sell_date'] = pd.to_datetime(transactions_df['sell_date'], errors='coerce')

    updated_rows = []

    for _, row in df.iterrows():
        symbol = row['symbol']
        try:
            current_price = float(row['current_price'])
        except ValueError:
            continue  # Skip rows with invalid prices

        # Find first open transaction for this symbol
        open_tx = transactions_df[
            (transactions_df['symbol'] == symbol) & (transactions_df['sell_date'].isna())
        ]

        if open_tx.empty:
            continue

        idx = open_tx.index[0]
        buy_value = pd.to_numeric(transactions_df.at[idx, 'current_price'], errors='coerce')

        if pd.isna(buy_value):
            continue

        # Calculate % benefit
        percentage_benefit = ((current_price - buy_value) / buy_value) * 100

        if percentage_benefit < revenue_percentage:
            continue

        # Fill sale details
        sell_date = datetime.today()
        transactions_df.loc[idx, 'sell_date'] = sell_date.strftime('%Y-%m-%d')
        transactions_df.loc[idx, 'sell_value'] = current_price
        transactions_df.loc[idx, 'buy_sell_days_diff'] = (sell_date - transactions_df.at[idx, 'buy_date']).days
        transactions_df.loc[idx, 'percentage_benefit'] = round(percentage_benefit, 2)

        updated_rows.append(transactions_df.loc[idx])

    # Save updated transactions
    transactions_df.to_csv(path, index=False)

    return pd.DataFrame(updated_rows)

def evaluate_buy_interest(symbol: str, df: pd.DataFrame, current_price: float) -> dict:
    """
    Evaluates whether to BUY, HOLD, or SELL a stock based on technical indicators.

    Parameters:
        symbol (str): Stock symbol
        df (pd.DataFrame): Historical data containing at least 'date' and 'close'
        current_price (float): Latest stock price

    Returns:
        dict: Analysis including decision, signals, and raw indicator values
    """
    print(f"Evaluating interest for {symbol}...")

    try:
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df['close'] = pd.to_numeric(df['close'], errors='coerce')

        # Calculate moving averages
        df["ma50"] = df["close"].rolling(window=50).mean()
        df["ma200"] = df["close"].rolling(window=200).mean()

        # RSI calculation
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # MACD
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["signal_line"] = df["macd"].ewm(span=9, adjust=False).mean()

        # Get last 2 rows for signal comparisons
        latest = df.iloc[-1]
        previous = df.iloc[-2]

        # Prepare raw signal values
        signals_dict = {
            "ma50": latest["ma50"],
            "ma200": latest["ma200"],
            "rsi": latest["rsi"],
            "macd": latest["macd"],
            "macd_signal": latest["signal_line"],
            "previous_macd": previous["macd"],
            "previous_macd_signal": previous["signal_line"],
            "current_price": current_price
        }

        active_signals = []
        buy_signals = 0
        sell_signals = 0

        # MA crossover
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
                active_signals.append(f"❌ RSI oversold ({rsi:.2f})")
                sell_signals += 1
            elif rsi > 80:
                active_signals.append(f"❌ RSI overbought ({rsi:.2f})")
                sell_signals += 1
            else:
                active_signals.append(f"⚠️ RSI neutral ({rsi:.2f})")

        # MACD crossover
        if all(pd.notna([previous["macd"], previous["signal_line"], latest["macd"], latest["signal_line"]])):
            if previous["macd"] < previous["signal_line"] and latest["macd"] > latest["signal_line"]:
                active_signals.append("✅ MACD bullish crossover")
                buy_signals += 1
            elif previous["macd"] > previous["signal_line"] and latest["macd"] < latest["signal_line"]:
                active_signals.append("❌ MACD bearish crossover")
                sell_signals += 1

        # Final decision
        if buy_signals > sell_signals:
            decision = "✅ BUY"
        elif sell_signals > buy_signals:
            decision = "❌ SELL"
        else:
            decision = "✋ HOLD"

        return {
            "symbol": symbol,
            "evaluation": decision,
            "active_signals": active_signals,
            "signals": signals_dict
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "evaluation": "⚠️ Evaluation failed",
            "active_signals": ["failed"],
            "signals": {"error": str(e)}
        }
