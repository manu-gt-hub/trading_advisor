"""
Layered deterministic technical engine.

This module is the SOLE decision maker of the technical system. It separates the
analysis into three independent, hierarchical layers:

  1. trend     -> directional structure (SMA, EMA, ADX direction)      [-1, 1]
  2. momentum  -> RSI + MACD (primary), Stoch RSI + ROC (secondary)    [-1, 1]
  3. risk      -> volatility, volume confirmation, divergences         [ 0, 1]

All indicators are normalized to a common scale BEFORE being aggregated into
sub-scores (trend_score, momentum_score, risk_score). A regime classifier
(SMA + ADX) gates the final, deterministic signal.

The output is structured and deterministic: signal + strength + regime +
sub-scores. No narrative language is produced here. The LLM never participates
in classification; it only audits BUY signals downstream.
"""

import os
import json
import math
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_CACHE = None
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "resources" / "technical_config.json"

# Single source of truth for the BUY threshold: the MIN_BUY_CONFIDENCE env var
# (the same knob used as the post-audit acceptance filter in main.py). This
# default is only used when the env var is not set (e.g. local runs / tests).
DEFAULT_BUY_THRESHOLD = 0.6


def resolve_buy_threshold(config: dict = None) -> float:
    """
    Resolve the BUY threshold from the MIN_BUY_CONFIDENCE env var so the engine
    and the downstream acceptance filter share one tunable knob (configurable
    from GitHub Actions without touching code or JSON).
    """
    config = config or load_config()
    default = config.get("decision", {}).get("buy_threshold_default", DEFAULT_BUY_THRESHOLD)
    try:
        return float(os.environ.get("MIN_BUY_CONFIDENCE", default))
    except (TypeError, ValueError):
        return float(default)


def load_config(force_reload: bool = False) -> dict:
    """Load (and cache) the technical configuration JSON."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None or force_reload:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _CONFIG_CACHE = json.load(f)
    return _CONFIG_CACHE


# ---------------------------------------------------------------------------
# Normalization helpers (common scale)
# ---------------------------------------------------------------------------
def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _tanh(value: float) -> float:
    return math.tanh(value)


def _safe(value, default=0.0) -> float:
    """Return a finite float or a default if value is None/NaN/inf."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return v


# ---------------------------------------------------------------------------
# Regime classifier (SMA + ADX)
# ---------------------------------------------------------------------------
def classify_regime(features: dict, config: dict = None) -> str:
    """
    Classify the market regime using SMA structure + ADX strength + directional
    movement. Returns one of: TRENDING_UP, TRENDING_DOWN, RANGE, DISTRIBUTION.
    """
    config = config or load_config()
    rcfg = config["regime"]
    adx_trend_min = rcfg["adx_trend_min"]

    adx = _safe(features.get("adx"), 0.0)
    sma50 = _safe(features.get("sma50"))
    sma200 = _safe(features.get("sma200"))
    price = _safe(features.get("price"))
    plus_di = _safe(features.get("plus_di"))
    minus_di = _safe(features.get("minus_di"))

    if adx < adx_trend_min:
        return "RANGE"

    bullish_structure = sma50 > sma200 and price > sma200
    bearish_structure = sma50 < sma200 and price < sma200
    directional_up = plus_di > minus_di
    directional_down = minus_di > plus_di

    if bullish_structure and directional_up:
        return "TRENDING_UP"
    if bearish_structure and directional_down:
        return "TRENDING_DOWN"
    # Bullish structure but selling pressure into highs -> topping / distribution
    if price > sma200 and directional_down:
        return "DISTRIBUTION"
    if bearish_structure and directional_up:
        return "RANGE"
    return "RANGE"


# ---------------------------------------------------------------------------
# Layer 1: TREND  -> [-1, 1]
# ---------------------------------------------------------------------------
def compute_trend_score(features: dict, config: dict = None):
    config = config or load_config()
    ind = config["layers"]["trend"]["indicators"]
    factors = {}

    sma50 = _safe(features.get("sma50"))
    sma200 = _safe(features.get("sma200"))
    ema20 = _safe(features.get("ema20"))
    price = _safe(features.get("price"))
    ma50_slope = _safe(features.get("ma50_slope"))
    adx = _safe(features.get("adx"))
    plus_di = _safe(features.get("plus_di"))
    minus_di = _safe(features.get("minus_di"))

    # sma_cross: relative gap scaled
    if sma200 != 0:
        gap = (sma50 - sma200) / abs(sma200)
        factors["sma_cross"] = _clip(_tanh(gap * 20), -1.0, 1.0)
    else:
        factors["sma_cross"] = 0.0

    # price vs SMA200
    if sma200 != 0:
        dist = (price - sma200) / abs(sma200)
        factors["price_vs_sma200"] = _clip(_tanh(dist * 10), -1.0, 1.0)
    else:
        factors["price_vs_sma200"] = 0.0

    # price vs EMA20 and SMA50
    above_ema = price > ema20 if ema20 else False
    above_sma = price > sma50 if sma50 else False
    if above_ema and above_sma:
        factors["price_vs_ema20_sma50"] = 1.0
    elif (not above_ema) and (not above_sma) and ema20 and sma50:
        factors["price_vs_ema20_sma50"] = -1.0
    else:
        factors["price_vs_ema20_sma50"] = 0.0

    # MA50 slope (normalize by price level)
    if price != 0:
        factors["ma50_slope"] = _clip(_tanh((ma50_slope / abs(price)) * 100), -1.0, 1.0)
    else:
        factors["ma50_slope"] = 0.0

    # ADX directional component
    denom = plus_di + minus_di
    if denom > 0:
        direction = (plus_di - minus_di) / denom
        strength = min(adx / 40.0, 1.0)
        factors["adx_direction"] = _clip(direction * strength, -1.0, 1.0)
    else:
        factors["adx_direction"] = 0.0

    # Weekly (higher timeframe) confirmation — OPTIONAL.
    # Only added when weekly history is sufficient; otherwise the remaining
    # trend weights are renormalized automatically by _weighted_average.
    if features.get("weekly_available"):
        wt = 1.0 if features.get("weekly_trend_bullish") else -1.0
        wp = 1.0 if features.get("weekly_price_above_ma10") else -1.0
        factors["weekly_confirmation"] = _clip(0.5 * wt + 0.5 * wp, -1.0, 1.0)

    score = _weighted_average(factors, ind)
    return _clip(score, -1.0, 1.0), factors


# ---------------------------------------------------------------------------
# Layer 2: MOMENTUM -> [-1, 1]  (RSI + MACD primary, Stoch RSI + ROC secondary)
# ---------------------------------------------------------------------------
def compute_momentum_score(features: dict, config: dict = None):
    config = config or load_config()
    ind = config["layers"]["momentum"]["indicators"]
    factors = {}

    rsi = _safe(features.get("rsi"), 50.0)
    macd = _safe(features.get("macd"))
    macd_signal = _safe(features.get("macd_signal"))
    macd_hist_slope = _safe(features.get("macd_hist_slope"))
    macd_cross = features.get("macd_cross", 0)  # +1 bull cross, -1 bear cross, 0 none
    stoch_k = _safe(features.get("stoch_rsi_k"), 50.0)
    roc = _safe(features.get("roc"))

    # RSI (primary)
    neutral = ind["rsi"]["params"]["neutral"]
    scale = ind["rsi"]["params"]["scale"]
    factors["rsi"] = _clip((rsi - neutral) / scale, -1.0, 1.0)

    # MACD (primary)
    sign_component = 0.5 if macd > macd_signal else (-0.5 if macd < macd_signal else 0.0)
    slope_component = 0.25 if macd_hist_slope > 0 else (-0.25 if macd_hist_slope < 0 else 0.0)
    cross_component = 0.25 * (1 if macd_cross > 0 else (-1 if macd_cross < 0 else 0))
    factors["macd"] = _clip(sign_component + slope_component + cross_component, -1.0, 1.0)

    # Stoch RSI (secondary)
    factors["stoch_rsi"] = _clip((stoch_k - 50.0) / 50.0, -1.0, 1.0)

    # ROC (secondary)
    roc_scale = ind["roc"]["params"]["scale"]
    factors["roc"] = _clip(_tanh(roc * roc_scale), -1.0, 1.0)

    score = _weighted_average(factors, ind)
    return _clip(score, -1.0, 1.0), factors


# ---------------------------------------------------------------------------
# Layer 3: RISK -> [0, 1]  (volume + divergences are risk factors)
# ---------------------------------------------------------------------------
def compute_risk_score(features: dict, config: dict = None):
    config = config or load_config()
    rcfg = config["layers"]["risk"]
    ind = rcfg["indicators"]
    factors = {}

    volatility = _safe(features.get("volatility"))
    rsi = _safe(features.get("rsi"), 50.0)
    price = _safe(features.get("price"))
    bb_upper = _safe(features.get("bb_upper"))

    # Volatility risk
    vol_high = ind["volatility"]["params"]["high_threshold"]
    factors["volatility"] = _clip(volatility / vol_high, 0.0, 1.0) if vol_high else 0.0

    # Volume confirmation risk
    volume = features.get("volume")
    vol_sma = features.get("vol_sma_20")
    obv = features.get("obv")
    obv_sma = features.get("obv_sma_20")
    vol_risk = 0.0
    if volume is not None and vol_sma is not None and _safe(vol_sma) > 0:
        if _safe(volume) < _safe(vol_sma):
            vol_risk += 0.5  # move not confirmed by participation
    if obv is not None and obv_sma is not None:
        if _safe(obv) < _safe(obv_sma):
            vol_risk += 0.5  # distribution / institutional selling
    if volume is None and obv is None:
        vol_risk = 0.3  # unknown volume -> mild risk
    factors["volume_confirmation"] = _clip(vol_risk, 0.0, 1.0)

    # Overbought risk
    overbought = ind["overbought"]["params"]["rsi_overbought"]
    ob_risk = _clip((rsi - overbought) / (100 - overbought), 0.0, 1.0)
    if bb_upper and price >= bb_upper:
        ob_risk = max(ob_risk, 0.6)
    factors["overbought"] = ob_risk

    # Divergence risk (bearish price/OBV or price/RSI divergence)
    factors["divergence"] = 1.0 if features.get("bearish_divergence") else 0.0

    score = _weighted_average(factors, ind)
    return _clip(score, 0.0, 1.0), factors


def _weighted_average(factors: dict, indicators_cfg: dict) -> float:
    """Weighted average of factor values using weights from the config."""
    total_weight = 0.0
    acc = 0.0
    for name, value in factors.items():
        weight = indicators_cfg.get(name, {}).get("weight", 0.0)
        acc += value * weight
        total_weight += weight
    return acc / total_weight if total_weight > 0 else 0.0


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------
def _strength_label(magnitude: float, config: dict) -> str:
    bands = config["decision"]["strength_bands"]
    if magnitude >= bands["STRONG"]:
        return "STRONG"
    if magnitude >= bands["MODERATE"]:
        return "MODERATE"
    return "WEAK"


def decide(features: dict, config: dict = None) -> dict:
    """
    Run the full layered evaluation and return a structured, deterministic result.

    Returns:
        {
          "signal": "BUY"|"SELL"|"HOLD",
          "strength": "WEAK"|"MODERATE"|"STRONG",
          "regime": "TRENDING_UP"|"TRENDING_DOWN"|"RANGE"|"DISTRIBUTION",
          "confidence": float in [-1, 1],
          "sub_scores": {"trend_score", "momentum_score", "risk_score"},
          "factors": {"trend": {...}, "momentum": {...}, "risk": {...}}
        }
    """
    config = config or load_config()
    dcfg = config["decision"]

    regime = classify_regime(features, config)
    trend_score, trend_factors = compute_trend_score(features, config)
    momentum_score, momentum_factors = compute_momentum_score(features, config)
    risk_score, risk_factors = compute_risk_score(features, config)

    w_trend = config["layers"]["trend"]["layer_weight"]
    w_momentum = config["layers"]["momentum"]["layer_weight"]
    total_w = w_trend + w_momentum
    directional = (trend_score * w_trend + momentum_score * w_momentum) / total_w

    penalty_factor = config["layers"]["risk"]["penalty_factor"]
    risk_adjusted = directional * (1.0 - penalty_factor * risk_score)
    confidence = _clip(risk_adjusted, -1.0, 1.0)

    # --- Deterministic, regime-gated decision ---
    buy_ok_regime = regime in dcfg["require_regime_for_buy"]
    sell_regime = regime in dcfg["sell_regimes"]
    buy_threshold = resolve_buy_threshold(config)

    if (buy_ok_regime
            and risk_adjusted >= buy_threshold
            and risk_score <= dcfg["max_risk_for_buy"]):
        signal = "BUY"
    elif risk_adjusted <= dcfg["strong_sell_threshold"]:
        signal = "SELL"
    elif sell_regime and risk_adjusted <= dcfg["sell_threshold"]:
        signal = "SELL"
    else:
        signal = "HOLD"

    strength = _strength_label(abs(risk_adjusted), config)

    return {
        "signal": signal,
        "strength": strength,
        "regime": regime,
        "confidence": round(confidence, 4),
        "sub_scores": {
            "trend_score": round(trend_score, 4),
            "momentum_score": round(momentum_score, 4),
            "risk_score": round(risk_score, 4),
        },
        "factors": {
            "trend": {k: round(v, 4) for k, v in trend_factors.items()},
            "momentum": {k: round(v, 4) for k, v in momentum_factors.items()},
            "risk": {k: round(v, 4) for k, v in risk_factors.items()},
        },
    }
