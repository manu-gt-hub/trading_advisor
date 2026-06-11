# Documentación — Trading Advisor

Esta carpeta documenta **en detalle** cómo el sistema analiza las métricas técnicas y genera las decisiones **BUY / HOLD / SELL**.

## Principio rector

> **El sistema técnico decide. El LLM solo audita.**

Un motor determinista por capas (`tools/technical_engine.py`) produce todas las señales. El LLM (GPT) se invoca **únicamente cuando la señal técnica es BUY** y solo puede (1) marcar incoherencias y (2) ajustar la confianza final dentro de límites. Nunca re-clasifica.

## Índice

| Documento | Contenido |
|---|---|
| [`01_arquitectura.md`](01_arquitectura.md) | Visión general, componentes y flujo de datos de extremo a extremo |
| [`02_indicadores_y_capas.md`](02_indicadores_y_capas.md) | Las 3 capas (trend / momentum / risk), cada indicador, su normalización y sus pesos |
| [`03_regimen_y_decision.md`](03_regimen_y_decision.md) | Clasificador de régimen (SMA + ADX) y cómo se generan BUY / HOLD / SELL |
| [`04_auditoria_llm.md`](04_auditoria_llm.md) | Rol exacto del LLM como auditor (coherencia + ajuste de confianza) |
| [`05_pipeline_y_filtros.md`](05_pipeline_y_filtros.md) | Pipeline de `main.py`: filtros de confianza, R:R, noticias, posiciones y correlación |
| [`06_configuracion.md`](06_configuracion.md) | `technical_config.json` y variables de entorno |

## Mapa rápido de código

```
tools/technical_engine.py     # Motor por capas + clasificador de régimen + decisión (DECISOR ÚNICO)
tools/custom_financial_calc.py# Cálculo de indicadores; construye el vector de features y delega en el motor
tools/llms.py                 # Auditor GPT (audit_buy_signal) + helpers legacy
tools/general.py              # Extracción de decisión + columna 'action' (técnica decide, LLM veta por incoherencia)
main.py                       # Orquesta el pipeline completo
resources/technical_config.json # Indicadores, pesos, reglas de régimen y umbrales
```

> Nota: los valores numéricos citados en estos documentos reflejan `resources/technical_config.json`. Si cambias el JSON, la lógica se adapta automáticamente (es config-driven); actualiza también estos `.md` si los pesos/umbrales cambian de forma relevante.
