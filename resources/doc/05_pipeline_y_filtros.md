# 05 — Pipeline de ejecución y filtros de cartera

Describe el flujo completo de `main.py`, desde la obtención de precios hasta guardar las recomendaciones. La señal técnica ya viene decidida por el motor; aquí se aplican **filtros de gestión de cartera** que solo pueden **bloquear** un BUY, nunca crear uno.

## Orden de ejecución (`main()`)

```
1. Guard de día de mercado         → si fin de semana/festivo US, no ejecuta
2. Obtener cotizaciones (Finnhub)  → precios actuales; normaliza símbolos (RHM.DE → RHM)
3. Análisis técnico por símbolo    → evaluate_buy_interest() → el MOTOR decide
4. Enriquecer DataFrame            → auditoría LLM (solo BUY) + etiquetas + SL/TP
5. Columna 'action'                → técnica decide; LLM veta BUY→HOLD si INCOHERENT
6. Filtro MIN_BUY_CONFIDENCE       → action==BUY y technical_confidence >= umbral
7. Filtro de posición abierta      → descarta BUY si ya hay posición sin vender
8. Filtro Riesgo/Recompensa (R:R)  → descarta BUY con R:R < 1.5
9. Filtro de noticias/earnings     → descarta BUY con earnings próximos o noticias muy negativas
10. Filtro de correlación          → elimina BUYs muy correlacionados (Pearson > 0.75)
11. Guardar en Google Drive        → recomendaciones BUY + análisis completo
```

## Paso 4 — Enriquecido (`enrich_analysis_df`)

Por cada símbolo:
- Si la señal es **BUY** → llama a `audit_buy_signal` (LLM), aplica el ajuste de confianza y guarda `llm_opinion = "COHERENT|INCOHERENT | adj=... | razón"`.
- Si **no** es BUY → no llama al LLM; `llm_opinion = "<EVAL> - LLM not called (technical decides)"`.
- Construye `manual_financial_analysis` (etiqueta determinista):
  `"<confianza> <SIGNAL> | regime=..., strength=..., trend=..., momentum=..., risk=... | RSI=..., MACD=..., ADX=..."`
- Guarda `technical_confidence` = **confianza ya auditada**.
- Calcula **stop-loss / take-profit / R:R** con `compute_stop_loss_take_profit` (ver abajo).

## Paso 5 — Columna `action` (`generate_action_column`)

Según `FORCE_OPINION`:

| Modo | Lógica |
|---|---|
| `DEFAULT` (recomendado) | `action` = decisión técnica (`manual_financial_analysis`); luego `apply_audit_veto` degrada BUY→HOLD si el LLM marcó INCOHERENT |
| `CUSTOM` | Solo técnica, sin veto del LLM |
| `LLM1` / `LLM2` | Legacy: usa la salida GPT directamente (no recomendado con el diseño actual) |

## Paso 6 — Filtro de confianza mínima

```python
buy_df = analysis_df[(action == 'BUY') & (technical_confidence >= MIN_BUY_CONFIDENCE)]
```

`MIN_BUY_CONFIDENCE` (env, por defecto `0.6`) es la **misma perilla** que usa el motor como umbral de BUY. Aquí actúa **post-auditoría**: captura los casos en que el LLM bajó la confianza por debajo del umbral. Los BUY descartados por baja confianza se registran en el log.

## Paso 7 — Posición abierta

Carga las transacciones; si el símbolo ya tiene una posición sin `sell_value`, se descarta el nuevo BUY (no se promedia ni se duplica).

## Paso 8 — Riesgo/Recompensa (`tools/risk_management.py`)

`compute_stop_loss_take_profit(precio, ATR, revenue_percentage)`:
- **Stop-loss** = `precio − 2·ATR`.
- **Take-profit** = el **más conservador** entre el objetivo `REVENUE_PERCENTAGE %` y `precio + 3·ATR`.
- **R:R** = `(take_profit − precio) / (precio − stop_loss)`.

Se **bloquea** el BUY si `R:R < 1.5`. Si el R:R es desconocido (`NaN`), no se bloquea.

## Paso 9 — Noticias y earnings (`tools/news_sentiment.py`)

`evaluate_news_filter(symbol, news_sentiment_enabled)` bloquea el BUY si:
- Hay **earnings próximos** (`earnings_soon`), o
- El sentimiento de noticias es marcadamente **negativo** (cuando `NEWS_SENT_ANALYSIS=true`).

> Earnings se tratan **aquí**, de forma determinista, **no** en el LLM.

## Paso 10 — Correlación (diversificación)

Si quedan ≥ 2 BUYs, `filter_correlated_buys(buy_df, max_correlation=0.75)` agrupa los muy correlacionados (Pearson > 0.75 sobre histórico reciente) y conserva, de cada grupo, el de **mayor `technical_confidence`**.

## Paso 11 — Salida

- **Buy Recommendations** (Google Drive): símbolos que pasaron todos los filtros + `buy_date`, `stop_loss`, `take_profit`, `risk_reward_ratio`, `tradingview_url`.
- **Analysis**: todos los símbolos con su evaluación, confianza, etiquetas y `action`.

## Mapa de bloqueos (todo lo que puede frenar un BUY)

| Etapa | Bloquea BUY si... |
|---|---|
| Auditoría LLM | el LLM marca INCOHERENT (→ HOLD) o baja la confianza |
| Confianza | `technical_confidence < MIN_BUY_CONFIDENCE` |
| Posición | ya existe posición abierta del símbolo |
| R:R | `risk_reward_ratio < 1.5` |
| Noticias | earnings próximos o sentimiento muy negativo |
| Correlación | correlación > 0.75 con otro BUY de mayor confianza |

Ningún filtro puede **crear** un BUY: la única fuente de BUY es el motor técnico.
