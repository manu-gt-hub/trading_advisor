# 04 — Auditoría con LLM (GPT)

## Principio

> El LLM **NO** es un segundo sistema de decisión. Es un **auditor**.

El motor técnico ya ha decidido. El LLM solo puede hacer dos cosas, y solo cuando la señal técnica es **BUY**:

1. **Detectar incoherencias** entre la salida estructurada (régimen, sub-scores) y los indicadores crudos.
2. **Ajustar la confianza final** dentro de límites estrechos.

**Nunca** re-clasifica (no convierte un HOLD/SELL en BUY, ni propone una decisión nueva).

## Cuándo se invoca

En `main.py` (`enrich_analysis_df`), solo si `evaluation == "BUY"`:

```python
if evaluation == "BUY":
    audit = llms.audit_buy_signal(metrics["signals"], symbol, current_price, technical_result)
    confidence = clip(confidence + audit["adjustment"], -1, 1)
    llm_opinion = f"{COHERENT|INCOHERENT} | adj={audit['adjustment']:+.2f} | {audit['reason']}"
```

Para SELL/HOLD **no se llama** al LLM (ahorro de coste de API).

## Qué recibe el auditor — `tools/llms.py`

`generate_audit_prompt` envía:
- La señal (BUY) y el precio.
- La salida estructurada: `regime`, `strength`, `trend_score`, `momentum_score`, `risk_score`.
- Los indicadores crudos (`signals`).
- El rango de ajuste permitido.

`audit_system_prompt` deja explícito que es un **auditor** que no puede cambiar la decisión, que solo verifica coherencia y propone un ajuste pequeño.

## Formato de salida del LLM

Una sola línea, parseada por `parse_audit_response`:

```
COHERENT|INCOHERENT | adjustment=<float> | <razón, máx 20 palabras>
```

`parse_audit_response` devuelve:

```python
{ "coherent": bool, "adjustment": float, "reason": str, "raw": str }
```

- `adjustment` se **recorta** al rango `confidence_adjustment_bounds` = `[-0.3, +0.1]` (asimétrico: puede penalizar mucho, premiar poco).
- Si el parseo falla o el LLM no está disponible, los valores por defecto son **conservadores**: `coherent = True`, `adjustment = 0.0` (no rescata ni hunde por error técnico).

## Cómo afecta a la decisión final

El LLM influye por **dos vías**, ambas sin re-clasificar:

### 1) Ajuste de confianza
`confidence` (técnica) `+= adjustment`. Como el umbral de aceptación de BUY (`MIN_BUY_CONFIDENCE`) se aplica **después**, un ajuste negativo puede dejar el BUY por debajo del umbral y descartarlo en el filtro de cartera.

### 2) Veto por incoherencia
En `tools/general.py`, `apply_audit_veto`:

```python
def apply_audit_veto(technical_decision, llm_opinion):
    if technical_decision == 'BUY' and 'INCOHERENT' in llm_opinion.upper():
        return 'HOLD'   # única acción permitida al LLM
    return technical_decision
```

- Si el auditor marca **INCOHERENT**, el BUY técnico se degrada a **HOLD**.
- El LLM **nunca** crea ni mejora una señal: a un SELL/HOLD no le hace nada; a un BUY solo puede bajarlo.

## Resumen de límites del LLM

| Acción del LLM | ¿Permitida? |
|---|---|
| Subir la confianza (hasta +0.1) | Sí |
| Bajar la confianza (hasta −0.3) | Sí |
| Degradar BUY → HOLD (incoherencia) | Sí |
| Convertir HOLD/SELL → BUY | **No** |
| Cambiar la clasificación / régimen | **No** |
| Decidir cuando la señal técnica no es BUY | **No** (ni se le llama) |

> Earnings y noticias **no** los gestiona el LLM: son datos deterministas y se filtran aparte (ver [`05_pipeline_y_filtros.md`](05_pipeline_y_filtros.md)).
