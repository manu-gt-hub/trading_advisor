# 06 — Configuración

Toda la lógica del motor es **config-driven**. Hay dos fuentes de configuración: el JSON de indicadores y las variables de entorno.

## A. `resources/technical_config.json`

Es la fuente de verdad de **indicadores, pesos, reglas de régimen y umbrales**. Editarlo cambia el comportamiento del motor sin tocar código.

### `regime`
```json
"adx_trend_min": 20.0,   // ADX mínimo para considerar que hay tendencia
"adx_strong": 25.0       // referencia de tendencia fuerte (informativa)
```

### `layers.trend` (peso de capa 0.55)
| Indicador | Peso | Opcional |
|---|---|---|
| `sma_cross` | 0.25 | no |
| `price_vs_sma200` | 0.15 | no |
| `price_vs_ema20_sma50` | 0.15 | no |
| `ma50_slope` | 0.10 | no |
| `adx_direction` | 0.15 | no |
| `weekly_confirmation` | 0.20 | **sí** (se omite si no hay histórico semanal; los demás se renormalizan) |

### `layers.momentum` (peso de capa 0.45)
| Indicador | Tier | Peso |
|---|---|---|
| `rsi` | primary | 0.35 |
| `macd` | primary | 0.35 |
| `stoch_rsi` | secondary | 0.15 |
| `roc` | secondary | 0.15 |

### `layers.risk` (`penalty_factor` 0.5)
| Indicador | Peso |
|---|---|
| `volatility` | 0.25 |
| `volume_confirmation` | 0.25 |
| `overbought` | 0.25 |
| `divergence` | 0.25 |

`risk_adjusted = directional · (1 − penalty_factor · risk_score)`.

### `decision`
```json
"buy_threshold_default": 0.6,        // fallback si MIN_BUY_CONFIDENCE no está definido
"sell_threshold": -0.35,             // SELL en regímenes bajistas
"strong_sell_threshold": -0.6,       // SELL en cualquier régimen
"max_risk_for_buy": 0.6,             // riesgo máximo tolerado para BUY
"require_regime_for_buy": ["TRENDING_UP"],
"sell_regimes": ["TRENDING_DOWN", "DISTRIBUTION"],
"strength_bands": { "STRONG": 0.7, "MODERATE": 0.45, "WEAK": 0.0 }
```

> El umbral de BUY **real** lo manda la variable de entorno `MIN_BUY_CONFIDENCE`; `buy_threshold_default` solo se usa si esa variable no está definida (runs locales / tests).

### `llm_audit`
```json
"enabled_only_on": "BUY",
"confidence_adjustment_bounds": [-0.3, 0.1],   // límites del ajuste del LLM
"incoherence_downgrades_to": "HOLD"
```

### Cómo se renormalizan los pesos
Dentro de cada capa los pesos son **relativos**. `_weighted_average` divide por la suma de los pesos de los indicadores **presentes**. Por eso `weekly_confirmation` puede faltar sin romper la escala: el resto se reparte el 100 %.

## B. Variables de entorno

| Variable | Descripción |
|---|---|
| `MIN_BUY_CONFIDENCE` | **Perilla única del umbral de BUY** (0.0–1.0, def. 0.6). El motor emite BUY solo si `risk_adjusted` la alcanza, y los BUY se aceptan post-auditoría contra el mismo valor |
| `FORCE_OPINION` | Modo de decisión: `DEFAULT` (técnica decide, LLM audita), `CUSTOM` (solo técnica), `LLM1`/`LLM2` (legacy) |
| `REVENUE_PERCENTAGE` | Objetivo de beneficio % para el take-profit |
| `OPENAI_API_KEY`, `GPT_MODEL_NAME` | Credenciales/modelo del auditor LLM |
| `FINNHUB_API_KEY`, `ALPHA_API_KEY`, `ALPHA_VANTAGE_URL` | Datos de mercado |
| `SYMBOLS_INTEREST_LIST` | Lista de tickers a analizar |
| `NEWS_SENT_ANALYSIS` | Activa el análisis de sentimiento de noticias (`true`/`false`) |
| `GDRIVE_*`, `BUY_RECOMMENDATIONS_ID`, `ANALYSIS_FILE_ID` | Persistencia en Google Drive |
| `TRANSACTIONS_MAX_RECORDS`, `LOG_LEVEL` | Operativa |

## C. Recetas de ajuste

| Quiero... | Cambio |
|---|---|
| **Más precisión / menos BUYs** | Sube `MIN_BUY_CONFIDENCE` (p. ej. 0.7) o baja `max_risk_for_buy` |
| **Más BUYs / más recall** | Baja `MIN_BUY_CONFIDENCE` (p. ej. 0.5) |
| **Dar más peso al multi-timeframe** | Sube `weekly_confirmation.weight` en la capa trend |
| **Penalizar más la volatilidad/riesgo** | Sube `penalty_factor` de la capa risk |
| **Exigir cruce MACD fresco con más peso** | Ajusta la fórmula de `macd` (en `technical_engine.compute_momentum_score`) |
| **Permitir BUY en RANGE** | Añade `"RANGE"` a `require_regime_for_buy` (no recomendado para precisión) |

## D. Tests relacionados

- `test/test_technical_engine.py` — capas, régimen, riesgo, weekly, umbral por env y parser de auditoría.
- `test/test_custom_financial_calc.py` — estructura de salida y robustez ante datos malos.
- `test/test_generals.py` — extracción de decisión y veto de auditoría.

```bash
pytest test/ -q --ignore=test/test_google_handler.py
```
