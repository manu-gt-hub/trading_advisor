# Documentation — Trading Advisor

This folder documents **in detail** how the system analyzes technical metrics and generates the **BUY / HOLD / SELL** decisions.

## Guiding principle

> **The technical system decides. The LLM only audits.**

A deterministic layered engine (`tools/technical_engine.py`) produces every signal. The LLM (GPT) is invoked **only when the technical signal is BUY** and can only (1) flag incoherences and (2) adjust the final confidence within bounds. It never re-classifies.

## Index

| Document | Content |
|---|---|
| [`01_architecture.md`](01_architecture.md) | Overview, components and end-to-end data flow |
| [`02_indicators_and_layers.md`](02_indicators_and_layers.md) | The 3 layers (trend / momentum / risk), each indicator, its normalization and weights |
| [`03_regime_and_decision.md`](03_regime_and_decision.md) | Regime classifier (SMA + ADX) and how BUY / HOLD / SELL are generated |
| [`04_llm_audit.md`](04_llm_audit.md) | The exact role of the LLM as an auditor (coherence + confidence adjustment) |
| [`05_pipeline_and_filters.md`](05_pipeline_and_filters.md) | The `main.py` pipeline: confidence, R:R, news, position and correlation filters |
| [`06_configuration.md`](06_configuration.md) | `technical_config.json` and environment variables |
| [`../../docs/BACKTEST_LOG.md`](../../docs/BACKTEST_LOG.md) | Backtest results history: baseline metrics, changes made, and before/after comparisons |

> **Important — backtest workflow for engine changes:**
>
> [`docs/BACKTEST_LOG.md`](../../docs/BACKTEST_LOG.md) is the **single source of truth** for measuring the prediction engine's quality. The latest entry is always the current baseline. Whenever you modify the prediction/decision engine (indicators, weights, regime rules, exit logic, trailing stop parameters, filters in `technical_engine.py`, `custom_financial_calc.py`, `technical_config.json`, or `main.py` pipeline):
>
> 1. **Run the backtest** (`python run_backtest_all.py`) **before and after** the change.
> 2. **Compare** the new results against the latest `BACKTEST_LOG.md` entry (the baseline): win rate, expectancy, profit factor, MAE/MFE, and per-symbol breakdown.
> 3. **Report to the user** with a clear before-vs-after summary, highlighting what improved and what degraded.
> 4. **Ask the user** whether to keep the changes or revert them.
> 5. If the user **approves**: append a new dated section to `BACKTEST_LOG.md` with the changes made, before/after tables, and any diagnostics. This becomes the new baseline.
> 6. If the user **rejects**: revert the code changes. Do not update `BACKTEST_LOG.md`.
>
> The file uses dated sections (`## YYYY-MM-DD — description`) as entries. Keep all entries in a single file for easy comparison — do not create separate files per date.

## Quick code map

```
tools/technical_engine.py       # Layered engine + regime classifier + decision (SOLE DECIDER)
tools/custom_financial_calc.py  # Indicator computation; builds the feature vector and delegates to the engine
tools/llms.py                   # GPT auditor (audit_buy_signal) + legacy helpers
tools/general.py                # Decision extraction + 'action' column (technical decides, LLM veto on incoherence)
main.py                         # Orchestrates the full pipeline
resources/technical_config.json # Indicators, weights, regime rules and thresholds
```

> Note: the numeric values cited in these documents reflect `resources/technical_config.json`. If you change the JSON, the logic adapts automatically (it is config-driven); also update these `.md` files if weights/thresholds change significantly.
