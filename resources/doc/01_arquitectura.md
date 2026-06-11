# 01 — Arquitectura y flujo de datos

## Visión general

El sistema convierte datos de precio/volumen en una decisión **BUY / HOLD / SELL** estructurada y determinista, y solo después somete los BUY a una auditoría del LLM.

```
Datos OHLCV ─▶ Indicadores ─▶ Vector de features ─▶ MOTOR POR CAPAS ─▶ {signal, strength, regime, sub_scores, confidence}
                                                          │
                                                          ├─ trend_score     [-1, 1]
                                                          ├─ momentum_score  [-1, 1]
                                                          └─ risk_score      [ 0, 1]
                                                          │
                                                   Clasificador de régimen (SMA + ADX)
                                                          │
                                          ┌───────────────┴───────────────┐
                                       ¿BUY?                            ¿SELL/HOLD?
                                          │                                │
                                  LLM AUDITA (coherencia + ajuste)     (sin LLM)
                                          │
                                  Filtros de cartera (confianza, R:R, noticias, posición, correlación)
                                          │
                                  Recomendación BUY → Google Drive
```

## Componentes

### 1. Cálculo de indicadores — `tools/custom_financial_calc.py`
`evaluate_buy_interest(symbol, df, current_price)`:
1. Limpia el `DataFrame` y exige **≥ 200 filas** de histórico.
2. Calcula todos los indicadores: SMA50/200, EMA20, RSI, MACD (+señal, histograma, pendiente), ROC, ADX (+DI/-DI), Stochastic RSI, OBV, Bollinger, ATR, volatilidad, breakout, Fibonacci, patrones de vela, confirmación semanal, contexto S&P500, probabilidad mensual.
3. Detecta **divergencia bajista** (factor de riesgo).
4. Construye un **vector de features** con los valores crudos.
5. Llama a `technical_engine.decide(features)` — **aquí se toma la decisión**.
6. Devuelve una salida estructurada (ver abajo). Los indicadores que no entran en el score (Bollinger, Fibonacci, velas, contexto, probabilidad mensual) se **reportan** en `signals` pero no afectan a la decisión.

### 2. Motor por capas — `tools/technical_engine.py`
**Es el único decisor.** Ver [`02_indicadores_y_capas.md`](02_indicadores_y_capas.md) y [`03_regimen_y_decision.md`](03_regimen_y_decision.md).

### 3. Auditor LLM — `tools/llms.py`
`audit_buy_signal(...)` se llama solo para BUY. Ver [`04_auditoria_llm.md`](04_auditoria_llm.md).

### 4. Orquestación y filtros — `main.py` + `tools/general.py`
Ver [`05_pipeline_y_filtros.md`](05_pipeline_y_filtros.md).

## Salida estructurada del motor

`evaluate_buy_interest` devuelve:

```python
{
  "symbol": "MSFT",
  "evaluation": "BUY",        # == signal (compatibilidad)
  "signal": "BUY",            # BUY | SELL | HOLD
  "strength": "STRONG",       # WEAK | MODERATE | STRONG
  "regime": "TRENDING_UP",    # TRENDING_UP | TRENDING_DOWN | RANGE | DISTRIBUTION
  "confidence": 0.74,         # score direccional ajustado por riesgo, en [-1, 1]
  "sub_scores": {
    "trend_score": 0.85,      # [-1, 1]
    "momentum_score": 0.68,   # [-1, 1]
    "risk_score": 0.06        # [ 0, 1]  (0 = sin riesgo, 1 = riesgo máximo)
  },
  "factors": {                # desglose determinista por capa
    "trend":    { "sma_cross": 0.96, "price_vs_sma200": 0.90, ... },
    "momentum": { "rsi": 0.60, "macd": 1.0, ... },
    "risk":     { "volatility": 0.25, "divergence": 0.0, ... }
  },
  "active_signals": [ "signal=BUY", "regime=TRENDING_UP", "trend.sma_cross=0.96", ... ],
  "signals": { ... todos los indicadores crudos reportados ... }
}
```

**Sin lenguaje narrativo**: `active_signals` son pares `clave=valor` deterministas, no frases.

## Determinismo

Dado el mismo vector de features, el motor produce **siempre** el mismo resultado (no hay aleatoriedad ni dependencia del LLM en la clasificación). Esto facilita el backtesting sin sesgo de look-ahead (`tools/backtesting.py`).
