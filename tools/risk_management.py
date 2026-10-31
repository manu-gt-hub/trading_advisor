import pandas as pd
import numpy as np
import logging
import yfinance as yf

logger = logging.getLogger(__name__)


def get_rules() -> dict:
    """Entry/exit rules from technical_config.json (shared by production and backtest)."""
    from tools import technical_engine
    return technical_engine.load_config().get("risk_management", {})


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
    if atr_14 is None or pd.isna(atr_14) or atr_14 <= 0 or current_price <= 0:
        return {"stop_loss": None, "take_profit": None, "risk_reward_ratio": None}

    rules = get_rules()
    stop_loss = round(current_price - rules.get("stop_loss_atr_mult", 2.0) * atr_14, 2)
    stop_loss = max(stop_loss, 0.01)  # floor at 0.01

    # Take-profit: use the more conservative of fixed % and N x ATR
    atr_target = round(current_price + rules.get("take_profit_atr_mult", 3.0) * atr_14, 2)
    if revenue_percentage:
        fixed_target = round(current_price * (1 + float(revenue_percentage) / 100), 2)
        take_profit = min(fixed_target, atr_target)  # use more conservative target
    else:
        take_profit = atr_target

    risk = current_price - stop_loss
    reward = take_profit - current_price
    risk_reward_ratio = round(reward / risk, 2) if risk > 0 else 0.0

    return {
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward_ratio": risk_reward_ratio,
    }


def update_open_position(buy_value, stop_loss, highest_price, current_price, target_price):
    """
    Advance an open position by one price observation. Single source of truth for
    exits: production (google_handler.update_transactions) and the backtester both
    call this, so a backtest replays exactly what production does.

    Trailing stop: once the highest price seen is >= trailing_activation_pct above
    buy_value, the stop ratchets to highest_price - (buy_value - stop_loss).

    Returns dict with the values to persist (highest_price, stop_loss, rounded to
    cents as stored in the sheet), trailed_from (previous stop when it moved, else
    None), exit_reason ('stop_loss' | 'take_profit' | None) and exit_price.
    """
    activation = get_rules().get("trailing_activation_pct", 2.0)
    stop_loss = pd.to_numeric(stop_loss, errors="coerce")
    highest_price = pd.to_numeric(highest_price, errors="coerce")
    new_highest = pd.isna(highest_price) or current_price > highest_price
    if new_highest:
        highest_price = current_price

    trailed_from = None
    gain_pct = ((highest_price - buy_value) / buy_value) * 100
    if gain_pct >= activation and pd.notna(stop_loss) and stop_loss > 0:
        original_risk = buy_value - stop_loss
        if original_risk > 0:
            trailing_stop = highest_price - original_risk
            if trailing_stop > stop_loss:
                trailed_from = stop_loss
                stop_loss = trailing_stop

    exit_reason, exit_price = None, None
    if pd.notna(stop_loss) and current_price <= stop_loss:
        exit_reason, exit_price = "stop_loss", float(stop_loss)
    elif current_price >= target_price:
        exit_reason, exit_price = "take_profit", float(target_price)

    return {
        "highest_price": round(float(highest_price), 2),
        "highest_changed": bool(new_highest),
        "stop_loss": round(float(stop_loss), 2) if pd.notna(stop_loss) else stop_loss,
        "trailed_from": trailed_from,
        "exit_reason": exit_reason,
        "exit_price": exit_price,
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

    max_position = portfolio_value * get_rules().get("max_position_pct", 20.0) / 100
    if position_value > max_position:
        shares = int(max_position / current_price)
        position_value = round(shares * current_price, 2)

    return {
        "shares": shares,
        "position_value": position_value,
        "risk_amount": round(risk_amount, 2),
    }


def filter_correlated_buys(buy_df, max_correlation=None, lookback_days=None):
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

    rules = get_rules()
    max_correlation = max_correlation if max_correlation is not None else rules.get("max_correlation", 0.75)
    lookback_days = lookback_days if lookback_days is not None else rules.get("correlation_lookback_days", 90)

    conf_col = "technical_confidence" if "technical_confidence" in buy_df.columns else None
    # Greedy keep-the-best: visit symbols by descending confidence so a kept symbol
    # is never removed later by a weaker one.
    ordered = buy_df.sort_values(conf_col, ascending=False, kind="stable") if conf_col else buy_df
    symbols = ordered["symbol"].tolist()

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

        # Each kept symbol removes every later (lower-confidence) symbol correlated with it
        removed = set()
        for i, sym_a in enumerate(symbols):
            if sym_a in removed:
                continue
            for sym_b in symbols[i + 1:]:
                if sym_b in removed:
                    continue
                if sym_a in corr_matrix.columns and sym_b in corr_matrix.columns:
                    corr = corr_matrix.loc[sym_a, sym_b]
                    if abs(corr) >= max_correlation:
                        removed.add(sym_b)
                        logger.info(
                            f"🚫 Diversification filter: removed {sym_b} (corr={corr:.2f} with {sym_a})"
                        )

        filtered = buy_df[~buy_df["symbol"].isin(removed)].copy()
        if len(removed) > 0:
            logger.info(f"Diversification filter removed {len(removed)} correlated positions: {removed}")
        return filtered

    except Exception as e:
        logger.warning(f"Correlation filter failed: {e}")
        return buy_df
