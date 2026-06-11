# 02 — Indicadores, capas y normalización

El sistema separa el análisis en **tres capas con jerarquía clara**. Cada indicador se **normaliza a una escala común** antes de agregarse. Las capas no se mezclan: cada una produce un *sub-score* independiente.

| Capa | Escala | Significado | Peso de capa |
|---|---|---|---|
| `trend` | `[-1, 1]` | Estructura direccional del precio | `0.55` |
| `momentum` | `[-1, 1]` | Velocidad/fuerza del movimiento | `0.45` |
| `risk` | `[0, 1]` | Penalización (0 = sin riesgo, 1 = riesgo máximo) | — (penaliza) |

> Todos los pesos viven en `resources/technical_config.json`. Dentro de cada capa los pesos son **relativos**: el agregador (`_weighted_average`) divide por la suma de los pesos de los indicadores presentes, de modo que si un indicador opcional falta, los demás se **renormalizan** automáticamente.

---

## Capa 1 — TREND `[-1, 1]`

Mide si la estructura del precio es alcista o bajista.

| Indicador | Peso | Normalización |
|---|---|---|
| `sma_cross` | 0.25 | `clip(tanh(((SMA50 − SMA200) / |SMA200|) · 20), −1, 1)` |
| `price_vs_sma200` | 0.15 | `clip(tanh(((precio − SMA200) / |SMA200|) · 10), −1, 1)` |
| `price_vs_ema20_sma50` | 0.15 | `+1` si precio > EMA20 y > SMA50; `−1` si < ambos; `0` mixto |
| `ma50_slope` | 0.10 | `clip(tanh((pendiente_MA50 / |precio|) · 100), −1, 1)` |
| `adx_direction` | 0.15 | `clip(((+DI − −DI)/(+DI + −DI)) · min(ADX/40, 1), −1, 1)` |
| `weekly_confirmation` | 0.20 *(opcional)* | `clip(0.5·(MA10w>MA30w ? +1 : −1) + 0.5·(precio>MA10w ? +1 : −1), −1, 1)` |

**`weekly_confirmation` (confirmación multi-timeframe):** confirma la tendencia diaria contra la **semanal** (MA10/MA30 semanales y precio vs MA10 semanal). Reduce falsos BUY provocados por ruido diario. Es **opcional**: si no hay suficiente histórico semanal (`_compute_weekly_confirmation` devuelve `None`), el factor se omite y el resto de pesos de la capa trend se renormalizan.

`trend_score` = media ponderada de los factores presentes.

---

## Capa 2 — MOMENTUM `[-1, 1]`

Mide la fuerza del movimiento. **RSI y MACD son PRIMARIOS** (peso alto); **Stoch RSI y ROC son SECUNDARIOS** (peso bajo). No se mezclan con el mismo peso para evitar redundancia.

| Indicador | Tier | Peso | Normalización |
|---|---|---|---|
| `rsi` | primary | 0.35 | `clip((RSI − 50) / 20, −1, 1)` |
| `macd` | primary | 0.35 | `clip(0.5·sign(MACD−Señal) + 0.25·sign(pendiente_hist) + 0.25·cruce, −1, 1)` |
| `stoch_rsi` | secondary | 0.15 | `clip((%K − 50) / 50, −1, 1)` |
| `roc` | secondary | 0.15 | `clip(tanh(ROC · 10), −1, 1)` |

Detalle de `macd`:
- `sign(MACD − Señal)` → ±0.5 (MACD por encima/debajo de su señal).
- `sign(pendiente_histograma)` → ±0.25 (el histograma sube/baja).
- `cruce` → ±0.25 si hay **cruce fresco** alcista/bajista en la última barra (`macd_cross`), 0 si no.

`momentum_score` = media ponderada.

---

## Capa 3 — RISK `[0, 1]`

Penalización del riesgo. **Volumen y divergencias viven AQUÍ**, no en momentum. `0` = sin riesgo, `1` = riesgo máximo.

| Indicador | Peso | Normalización |
|---|---|---|
| `volatility` | 0.25 | `clip(volatilidad_20 / 0.04, 0, 1)` |
| `volume_confirmation` | 0.25 | `+0.5` si volumen < SMA20 de volumen; `+0.5` si OBV < SMA20 de OBV; `0.3` si no hay datos de volumen |
| `overbought` | 0.25 | `clip((RSI − 70)/30, 0, 1)`; se eleva a `≥ 0.6` si el precio toca/supera la banda de Bollinger superior |
| `divergence` | 0.25 | `1.0` si hay divergencia bajista precio/OBV o precio/RSI; `0` si no |

**Divergencia bajista** (`_detect_bearish_divergence`): el precio hace un máximo más alto mientras el OBV o el RSI hacen un máximo más bajo en una ventana de 14 barras → señal de agotamiento → **riesgo**, nunca momentum.

`risk_score` = media ponderada (siempre en `[0, 1]`).

---

## Indicadores reportados pero NO puntuados

Se calculan y aparecen en `signals` para inspección/auditoría, pero **no entran en el score**:
- Bandas de Bollinger (salvo que el precio toque la superior → entra como riesgo `overbought`).
- Niveles de Fibonacci (38.2 / 50 / 61.8 %).
- Patrones de vela (Hammer, Engulfing, Doji, Shooting Star).
- Contexto de mercado S&P500 (`Market_Trend`).
- Probabilidad histórica mensual de +10 % (`Monthly_10pct_Prob`).

Esto mantiene la jerarquía limpia: solo entran al score los factores con un rol claro en trend / momentum / risk.
