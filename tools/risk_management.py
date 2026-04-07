import pandas as pd
import numpy as np
import logging
import yfinance as yf

logger = logging.getLogger(__name__)


def compute_stop_loss_take_profit(current_price, atr_14, revenue_percentage=None):
    """
    Compute ATR-based stop-loss and take-profit levels.

    Parameters:
        current_price (float): Current stock price.
        atr_14 (float): Average True Range over 14 periods.
        revenue_percentage (float, optional): Target profit % from env config.

    Returns:
        dict with stop_loss, take_profit, and risk_reward_ratio.
    """
    if pd.isna(atr_14) or atr_14 <= 0 or current_price <= 0:
        return {"stop_loss": None, "take_profit": None, "risk_reward_ratio": None}

    # Stop-loss: 2x ATR below current price
    stop_loss = round(current_price - 2.0 * atr_14, 2)
    stop_loss = max(stop_loss, 0.01)  # floor at 0.01

    # Take-profit: use revenue_percentage if available, else 3x ATR
    if revenue_percentage:
        take_profit = round(current_price * (1 + float(revenue_percentage) / 100), 2)
    else:
        take_profit = round(current_price + 3.0 * atr_14, 2)

    risk = current_price - stop_loss
    reward = take_profit - current_price
    risk_reward_ratio = round(reward / risk, 2) if risk > 0 else 0.0

    return {
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward_ratio": risk_reward_ratio,
    }


def compute_position_size(portfolio_value, risk_per_trade_pct, current_price, stop_loss):
    """
    Compute position size based on fixed-risk model.

    Parameters:
        portfolio_value (float): Total portfolio value in $.
        risk_per_trade_pct (float): Max % of portfolio to risk per trade (e.g., 2.0).
        current_price (float): Current stock price.
        stop_loss (float): Stop-loss price level.

    Returns:
        dict with shares, position_value, and risk_amount.
    """
    if not all([portfolio_value, current_price, stop_loss]) or current_price <= 0:
        return {"shares": 0, "position_value": 0.0, "risk_amount": 0.0}

    risk_amount = portfolio_value * (risk_per_trade_pct / 100)
    risk_per_share = current_price - stop_loss

    if risk_per_share <= 0:
        return {"shares": 0, "position_value": 0.0, "risk_amount": risk_amount}

    shares = int(risk_amount / risk_per_share)
    position_value = round(shares * current_price, 2)

    # Cap at 20% of portfolio per position
    max_position = portfolio_value * 0.20
    if position_value > max_position:
        shares = int(max_position / current_price)
        position_value = round(shares * current_price, 2)

    return {
        "shares": shares,
        "position_value": position_value,
        "risk_amount": round(risk_amount, 2),
    }


def filter_correlated_buys(buy_df, max_correlation=0.75, lookback_days=90):
    """
    Filter out highly correlated BUY recommendations to ensure diversification.
    Keeps the highest-confidence symbol from each correlated cluster.

    Parameters:
        buy_df (pd.DataFrame): DataFrame with BUY recommendations (must have 'symbol' and 'technical_confidence').
        max_correlation (float): Maximum allowed Pearson correlation between two positions.
        lookback_days (int): Days of price history to compute correlations.

    Returns:
        pd.DataFrame: Filtered buy recommendations with correlated duplicates removed.
    """
    if buy_df.empty or len(buy_df) < 2:
        return buy_df

    symbols = buy_df["symbol"].tolist()

    # Fetch recent close prices for correlation
    try:
        price_data = {}
        for sym in symbols:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period=f"{lookback_days}d")
            if hist is not None and not hist.empty:
                price_data[sym] = hist["Close"]

        if len(price_data) < 2:
            return buy_df

        prices_df = pd.DataFrame(price_data).dropna()
        if len(prices_df) < 20:
            logger.warning("Insufficient overlapping price data for correlation analysis")
            return buy_df

        returns_df = prices_df.pct_change().dropna()
        corr_matrix = returns_df.corr()

        # Find correlated pairs and remove the one with lower confidence
        removed = set()
        conf_col = "technical_confidence" if "technical_confidence" in buy_df.columns else None

        for i, sym_a in enumerate(symbols):
            if sym_a in removed:
                continue
            for sym_b in symbols[i + 1:]:
                if sym_b in removed:
                    continue
                if sym_a in corr_matrix.columns and sym_b in corr_matrix.columns:
                    corr = corr_matrix.loc[sym_a, sym_b]
                    if abs(corr) >= max_correlation:
                        # Remove the one with lower confidence
                        if conf_col:
                            conf_a = buy_df.loc[buy_df["symbol"] == sym_a, conf_col].values[0]
                            conf_b = buy_df.loc[buy_df["symbol"] == sym_b, conf_col].values[0]
                            loser = sym_b if conf_a >= conf_b else sym_a
                        else:
                            loser = sym_b
                        removed.add(loser)
                        logger.info(
                            f"Diversification filter: removed {loser} (corr={corr:.2f} with "
                            f"{'sym_a' if loser == sym_b else 'sym_b'})"
                        )

        filtered = buy_df[~buy_df["symbol"].isin(removed)].copy()
        if len(removed) > 0:
            logger.info(f"Diversification filter removed {len(removed)} correlated positions: {removed}")
        return filtered

    except Exception as e:
        logger.warning(f"Correlation filter failed: {e}")
        return buy_df
