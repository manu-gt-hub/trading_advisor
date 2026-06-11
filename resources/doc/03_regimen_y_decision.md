# 03 — Régimen y generación de BUY / HOLD / SELL

Este documento describe cómo el motor pasa de los tres *sub-scores* a una señal final. Todo es **determinista** y está en `tools/technical_engine.py` (`classify_regime` y `decide`).

## Paso 1 — Clasificador de régimen (SMA + ADX)

El régimen describe el **contexto** del mercado. Se calcula **solo** con SMA(50/200), ADX y la dirección (+DI/−DI). Hay exactamente 4 clases.

Variables:
- `bullish_structure` = `SMA50 > SMA200` **y** `precio > SMA200`
- `bearish_structure` = `SMA50 < SMA200` **y** `precio < SMA200`
- `adx_trend_min = 20` (umbral de existencia de tendencia)

Reglas (en orden):

| Orden | Condición | Régimen |
|---|---|---|
| 1 | `ADX < 20` | **RANGE** (sin tendencia dominante) |
| 2 | `bullish_structure` y `+DI > −DI` | **TRENDING_UP** |
| 3 | `bearish_structure` y `−DI > +DI` | **TRENDING_DOWN** |
| 4 | `precio > SMA200` y `−DI > +DI` | **DISTRIBUTION** (estructura alcista pero presión vendedora en máximos) |
| 5 | `bearish_structure` y `+DI > −DI` | **RANGE** |
| — | cualquier otro caso | **RANGE** (fallback) |

> `DISTRIBUTION` captura el típico "techo": el precio sigue por encima de la SMA200 pero la dirección ya es bajista (−DI domina). Es un régimen de **venta**, no de compra.

## Paso 2 — Agregación de capas

```
directional   = (trend_score · 0.55 + momentum_score · 0.45) / (0.55 + 0.45)
risk_adjusted = directional · (1 − 0.5 · risk_score)
confidence    = clip(risk_adjusted, −1, 1)
```

- `directional` ∈ `[-1, 1]`: dirección pura (trend + momentum ponderados por el peso de capa).
- El **riesgo penaliza multiplicativamente**: con `risk_score = 1`, la confianza se reduce a la mitad (`penalty_factor = 0.5`).
- `confidence` es el número que después se compara con los umbrales y que el LLM puede ajustar.

## Paso 3 — Decisión gateada por régimen

`buy_threshold` = variable de entorno **`MIN_BUY_CONFIDENCE`** (por defecto `0.6`). Es la **única perilla** del umbral de BUY (ver [`06_configuracion.md`](06_configuracion.md)).

```
SI  regime == TRENDING_UP
    Y risk_adjusted >= buy_threshold        (0.6 por defecto)
    Y risk_score   <= max_risk_for_buy      (0.6)
        → BUY

SI NO, SI risk_adjusted <= strong_sell_threshold   (−0.6)
        → SELL

SI NO, SI regime ∈ {TRENDING_DOWN, DISTRIBUTION}
        Y risk_adjusted <= sell_threshold          (−0.35)
        → SELL

EN OTRO CASO
        → HOLD
```

Consecuencias clave (alineadas con el objetivo de **alta precisión**):
- **Solo se compra en `TRENDING_UP`.** En `RANGE` o `DISTRIBUTION` nunca hay BUY, por muy alto que sea el momentum.
- Un **riesgo alto bloquea el BUY** aunque la dirección sea fuerte (`risk_score > 0.6`).
- La venta es más permisiva: un desplome fuerte (`risk_adjusted ≤ −0.6`) genera SELL en cualquier régimen; en regímenes bajistas basta `≤ −0.35`.

## Paso 4 — Fuerza de la señal (`strength`)

A partir de `|risk_adjusted|`:

| `|risk_adjusted|` | `strength` |
|---|---|
| ≥ 0.70 | **STRONG** |
| ≥ 0.45 | **MODERATE** |
| < 0.45 | **WEAK** |

`strength` es informativa (acompaña a la señal); no cambia la clasificación por sí sola.

## Ejemplo numérico (BUY)

Con un caso claramente alcista en `TRENDING_UP`:
- `trend_score ≈ 0.85`, `momentum_score ≈ 0.68`, `risk_score ≈ 0.06`.
- `directional = 0.85·0.55 + 0.68·0.45 = 0.77`.
- `risk_adjusted = 0.77 · (1 − 0.5·0.06) = 0.747`.
- `0.747 ≥ 0.6` y `0.06 ≤ 0.6` y régimen `TRENDING_UP` → **BUY**, `confidence ≈ 0.75`, `strength = STRONG`.

## Qué pasa después de la señal

- Si la señal es **BUY** → se somete a la **auditoría del LLM** ([`04_auditoria_llm.md`](04_auditoria_llm.md)) y a los **filtros de cartera** ([`05_pipeline_y_filtros.md`](05_pipeline_y_filtros.md)).
- Si es **SELL/HOLD** → no se llama al LLM (ahorro de coste); la señal fluye tal cual.
