# 06 — Configuration

All engine logic is **config-driven**. There are two configuration sources: the indicator JSON and the environment variables.

## A. `resources/technical_config.json`

This is the source of truth for **indicators, weights, regime rules and thresholds**. Editing it changes the engine behavior without touching code.

### `regime`
```json
"adx_trend_min": 20.0,   // minimum ADX to consider that a trend exists
"adx_strong": 25.0       // strong-trend reference (informational)
```

### `layers.trend` (layer weight 0.55)
| Indicator | Weight | Optional |
|---|---|---|
| `sma_cross` | 0.25 | no |
| `price_vs_sma200` | 0.15 | no |
| `price_vs_ema20_sma50` | 0.15 | no |
| `ma50_slope` | 0.10 | no |
| `adx_direction` | 0.15 | no |
| `weekly_confirmation` | 0.20 | **yes** (omitted if no weekly history; the rest are renormalized) |

### `layers.momentum` (layer weight 0.45)
| Indicator | Tier | Weight |
|---|---|---|
| `rsi` | primary | 0.35 |
| `macd` | primary | 0.35 |
| `stoch_rsi` | secondary | 0.15 |
| `roc` | secondary | 0.15 |

### `layers.risk` (`penalty_factor` 0.5)
| Indicator | Weight |
|---|---|
| `volatility` | 0.25 |
| `volume_confirmation` | 0.25 |
| `overbought` | 0.25 |
| `divergence` | 0.25 |

`risk_adjusted = directional * (1 - penalty_factor * risk_score)`.

### `decision`
```json
"buy_threshold_default": 0.6,        // fallback if MIN_BUY_CONFIDENCE is not set
"sell_threshold": -0.35,             // SELL in bearish regimes
"strong_sell_threshold": -0.6,       // SELL in any regime
"max_risk_for_buy": 0.6,             // maximum risk tolerated for BUY
"require_regime_for_buy": ["TRENDING_UP"],
"sell_regimes": ["TRENDING_DOWN", "DISTRIBUTION"],
"strength_bands": { "STRONG": 0.7, "MODERATE": 0.45, "WEAK": 0.0 }
```

> The **real** BUY threshold is driven by the `MIN_BUY_CONFIDENCE` environment variable; `buy_threshold_default` is only used if that variable is not set (local runs / tests).

### `llm_audit`
```json
"enabled_only_on": "BUY",
"confidence_adjustment_bounds": [-0.3, 0.1],   // LLM adjustment bounds
"incoherence_downgrades_to": "HOLD"
```

### How weights are renormalized
Within each layer the weights are **relative**. `_weighted_average` divides by the sum of the weights of the **present** indicators. That is why `weekly_confirmation` can be missing without breaking the scale: the rest share the 100%.

## B. Environment variables

| Variable | Description |
|---|---|
| `MIN_BUY_CONFIDENCE` | **Single BUY-threshold knob** (0.0-1.0, def. 0.6). The engine emits BUY only if `risk_adjusted` reaches it, and BUYs are accepted post-audit against the same value |
| `FORCE_OPINION` | Decision mode: `DEFAULT` (technical decides, LLM audits), `CUSTOM` (technical only), `LLM1`/`LLM2` (legacy) |
| `REVENUE_PERCENTAGE` | Target profit % for the take-profit |
| `OPENAI_API_KEY`, `GPT_MODEL_NAME` | LLM auditor credentials/model |
| `FINNHUB_API_KEY`, `ALPHA_API_KEY`, `ALPHA_VANTAGE_URL` | Market data |
| `SYMBOLS_INTEREST_LIST` | List of tickers to analyze |
| `NEWS_SENT_ANALYSIS` | Enables news sentiment analysis (`true`/`false`) |
| `GDRIVE_*`, `BUY_RECOMMENDATIONS_ID`, `ANALYSIS_FILE_ID` | Google Drive persistence |
| `TRANSACTIONS_MAX_RECORDS`, `LOG_LEVEL` | Operations |

## C. Tuning recipes

| I want to... | Change |
|---|---|
| **More precision / fewer BUYs** | Raise `MIN_BUY_CONFIDENCE` (e.g. 0.7) or lower `max_risk_for_buy` |
| **More BUYs / more recall** | Lower `MIN_BUY_CONFIDENCE` (e.g. 0.5) |
| **Give more weight to multi-timeframe** | Raise `weekly_confirmation.weight` in the trend layer |
| **Penalize volatility/risk more** | Raise the risk layer `penalty_factor` |
| **Weight fresh MACD crossover more** | Adjust the `macd` formula (in `technical_engine.compute_momentum_score`) |
| **Allow BUY in RANGE** | Add `"RANGE"` to `require_regime_for_buy` (not recommended for precision) |

## D. Related tests

- `test/test_technical_engine.py` — layers, regime, risk, weekly, env threshold and audit parser.
- `test/test_custom_financial_calc.py` — output structure and robustness against bad data.
- `test/test_generals.py` — decision extraction and audit veto.

```bash
pytest test/ -q --ignore=test/test_google_handler.py
```
