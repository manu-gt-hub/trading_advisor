# POLICY: Backtest validation (HARD RULE)

## Scope — what counts as an "engine change"

Any modification to the prediction/decision path:

- `tools/technical_engine.py` — layers, regime classifier, aggregation, thresholds
- `tools/custom_financial_calc.py` — indicator math, feature vector
- `tools/risk_management.py` — stop/target/sizing/correlation logic
- `tools/backtesting.py` — the evaluator itself (see special note below)
- `main.py` — filter pipeline, trailing stop, position management
- `resources/technical_config.json` — ANY value, weight, or threshold

## Mandatory procedure

1. **BEFORE**: run `python run_backtest_all.py`, save output (or diff vs latest
   `docs/BACKTEST_LOG.md` entry — the baseline).
2. **AFTER**: run `python run_backtest_all.py` again.
3. **COMPARE**: win rate, avg return/trade, expectancy, profit factor,
   exit-reason mix, MAE/MFE, per-symbol table.
4. **REPORT** to the user a before/after table and ask: **keep or revert?**
5. **APPROVED** → update `docs/BACKTEST_LOG.md` (new dated entry, becomes new
   baseline) → then request commit confirmation per `commit_policy.md`.
6. **REJECTED** → revert code. Do NOT touch `BACKTEST_LOG.md`. Do NOT commit.

## Forbidden

- Committing an engine change without showing a before/after backtest report.
- Updating `BACKTEST_LOG.md` without user approval.
- Claiming improvement based on intuition or a single metric — expectancy AND
  profit factor must both be considered, plus per-symbol breakdown.
- Cherry-picking the winning symbol — consolidated AND per-symbol tables required.

## Special note: changes to `backtesting.py`

The backtester is the measuring instrument. Changes to it do not need a
before/after comparison of *engine* quality, but DO need:
- the test suite green,
- a statement of what the metric change means for comparability of past
  `BACKTEST_LOG.md` entries (are old baselines still comparable?),
- a note in the next `BACKTEST_LOG.md` entry if comparability broke.

## Evidence: why this rule exists

- Trailing stop relaxed (2.5→3.5×ATR, +2%→+4%): looked better in theory,
  expectancy fell −0.52pp, PF fell −0.39. **Reverted.**
- `min_momentum_for_buy` 0.2→0.35: no historical change (most signals already
  above), kept for production filtering.
