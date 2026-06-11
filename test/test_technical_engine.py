import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import technical_engine as te
from tools.llms import parse_audit_response


def _bullish_features():
    return {
        "price": 115.0,
        "sma50": 110.0, "sma200": 100.0, "ema20": 113.0, "ma50_slope": 2.0,
        "adx": 30.0, "plus_di": 30.0, "minus_di": 10.0,
        "rsi": 62.0, "macd": 1.5, "macd_signal": 1.0, "macd_hist_slope": 0.2,
        "macd_cross": 1, "stoch_rsi_k": 70.0, "roc": 0.04,
        "volatility": 0.01, "bb_upper": 130.0, "bearish_divergence": False,
        "volume": 2000.0, "vol_sma_20": 1000.0, "obv": 5000.0, "obv_sma_20": 4000.0,
    }


def _bearish_features():
    return {
        "price": 85.0,
        "sma50": 90.0, "sma200": 100.0, "ema20": 87.0, "ma50_slope": -2.0,
        "adx": 30.0, "plus_di": 10.0, "minus_di": 30.0,
        "rsi": 38.0, "macd": -1.5, "macd_signal": -1.0, "macd_hist_slope": -0.2,
        "macd_cross": -1, "stoch_rsi_k": 30.0, "roc": -0.04,
        "volatility": 0.03, "bb_upper": 95.0, "bearish_divergence": True,
        "volume": 500.0, "vol_sma_20": 1000.0, "obv": 3000.0, "obv_sma_20": 4000.0,
    }


# --- config ---
def test_config_loads_three_layers():
    cfg = te.load_config()
    assert set(cfg["layers"].keys()) == {"trend", "momentum", "risk"}
    # primary momentum indicators must outweigh secondary ones
    mom = cfg["layers"]["momentum"]["indicators"]
    assert mom["rsi"]["weight"] > mom["stoch_rsi"]["weight"]
    assert mom["macd"]["weight"] > mom["roc"]["weight"]


# --- regime classifier (SMA + ADX) ---
def test_regime_trending_up():
    assert te.classify_regime(_bullish_features()) == "TRENDING_UP"


def test_regime_trending_down():
    assert te.classify_regime(_bearish_features()) == "TRENDING_DOWN"


def test_regime_range_when_adx_weak():
    f = _bullish_features()
    f["adx"] = 10.0  # below adx_trend_min
    assert te.classify_regime(f) == "RANGE"


def test_regime_distribution():
    # Bullish structure (price > SMA200) but selling pressure (-DI > +DI)
    f = _bullish_features()
    f["plus_di"], f["minus_di"] = 10.0, 30.0
    f["sma50"] = 95.0  # not a clean bearish structure, price still > sma200
    assert te.classify_regime(f) == "DISTRIBUTION"


# --- sub-scores ---
def test_sub_scores_ranges():
    res = te.decide(_bullish_features())
    sub = res["sub_scores"]
    assert -1.0 <= sub["trend_score"] <= 1.0
    assert -1.0 <= sub["momentum_score"] <= 1.0
    assert 0.0 <= sub["risk_score"] <= 1.0


def test_weekly_confirmation_is_optional():
    # Without weekly data the trend factor is omitted (weights renormalized)
    res = te.decide(_bullish_features())
    assert "weekly_confirmation" not in res["factors"]["trend"]


def test_weekly_bullish_boosts_trend():
    base = _bullish_features()
    res_no = te.decide(base)

    bull = dict(base)
    bull["weekly_available"] = True
    bull["weekly_trend_bullish"] = True
    bull["weekly_price_above_ma10"] = True
    res_bull = te.decide(bull)

    assert res_bull["factors"]["trend"]["weekly_confirmation"] == 1.0
    assert res_bull["sub_scores"]["trend_score"] >= res_no["sub_scores"]["trend_score"]


def test_weekly_bearish_reduces_trend():
    base = _bullish_features()
    res_no = te.decide(base)

    bear = dict(base)
    bear["weekly_available"] = True
    bear["weekly_trend_bullish"] = False
    bear["weekly_price_above_ma10"] = False
    res_bear = te.decide(bear)

    assert res_bear["factors"]["trend"]["weekly_confirmation"] == -1.0
    assert res_bear["sub_scores"]["trend_score"] < res_no["sub_scores"]["trend_score"]


def test_weekly_is_a_trend_factor_not_momentum():
    base = _bullish_features()
    res_no = te.decide(base)
    wk = dict(base)
    wk["weekly_available"] = True
    wk["weekly_trend_bullish"] = False
    wk["weekly_price_above_ma10"] = False
    res_wk = te.decide(wk)
    # momentum must be untouched by the weekly (trend) factor
    assert res_wk["sub_scores"]["momentum_score"] == res_no["sub_scores"]["momentum_score"]


def test_divergence_is_risk_not_momentum():
    base = _bullish_features()
    res_no = te.decide(base)
    div = dict(base)
    div["bearish_divergence"] = True
    res_div = te.decide(div)
    # momentum unchanged, risk increases
    assert res_div["sub_scores"]["momentum_score"] == res_no["sub_scores"]["momentum_score"]
    assert res_div["sub_scores"]["risk_score"] > res_no["sub_scores"]["risk_score"]


# --- deterministic decision ---
def test_bullish_trending_up_yields_buy():
    res = te.decide(_bullish_features())
    assert res["signal"] == "BUY"
    assert res["regime"] == "TRENDING_UP"
    assert res["confidence"] > 0


def test_bearish_trending_down_yields_sell():
    res = te.decide(_bearish_features())
    assert res["signal"] == "SELL"
    assert res["confidence"] < 0


def test_buy_threshold_follows_min_buy_confidence_env(monkeypatch):
    # Single knob: MIN_BUY_CONFIDENCE drives the engine's BUY threshold
    f = _bullish_features()  # risk_adjusted ~0.74 -> BUY by default
    assert te.decide(f)["signal"] == "BUY"

    monkeypatch.setenv("MIN_BUY_CONFIDENCE", "0.95")
    assert te.resolve_buy_threshold() == 0.95
    assert te.decide(f)["signal"] != "BUY"  # 0.74 < 0.95 now blocks the BUY

    monkeypatch.delenv("MIN_BUY_CONFIDENCE", raising=False)
    assert te.decide(f)["signal"] == "BUY"


def test_buy_requires_trending_up_regime():
    # Strong momentum but RANGE regime (weak ADX) must NOT produce BUY
    f = _bullish_features()
    f["adx"] = 12.0
    res = te.decide(f)
    assert res["regime"] == "RANGE"
    assert res["signal"] != "BUY"


def test_high_risk_blocks_buy():
    f = _bullish_features()
    f["bearish_divergence"] = True
    f["volatility"] = 0.08
    f["volume"], f["vol_sma_20"] = 500.0, 1000.0
    f["obv"], f["obv_sma_20"] = 3000.0, 4000.0
    res = te.decide(f)
    assert res["sub_scores"]["risk_score"] > 0.6
    assert res["signal"] != "BUY"


def test_decide_is_deterministic():
    f = _bullish_features()
    assert te.decide(f) == te.decide(f)


def test_output_is_structured_no_narrative():
    res = te.decide(_bullish_features())
    assert set(res.keys()) >= {"signal", "strength", "regime", "confidence", "sub_scores", "factors"}
    assert res["strength"] in {"WEAK", "MODERATE", "STRONG"}


# --- audit parser ---
def test_parse_audit_response_coherent():
    out = parse_audit_response("COHERENT | adjustment=0.08 | trend aligned", [-0.3, 0.1])
    assert out["coherent"] is True
    assert out["adjustment"] == 0.08


def test_parse_audit_response_incoherent_and_bounds():
    out = parse_audit_response("INCOHERENT | adjustment=-0.95 | divergence", [-0.3, 0.1])
    assert out["coherent"] is False
    assert out["adjustment"] == -0.3  # clamped to lower bound


def test_parse_audit_response_defaults_when_unparseable():
    out = parse_audit_response(None, [-0.3, 0.1])
    assert out["coherent"] is True
    assert out["adjustment"] == 0.0
