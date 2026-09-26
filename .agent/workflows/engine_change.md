# WORKFLOW: Engine change (config, weights, thresholds, exit logic)

Use for ANY change in the decision path — see `policies/backtest_policy.md` for scope.

## Steps

```
1. BASELINE   → python run_backtest_all.py        (record/save output)
2. CHANGE     → edit code or technical_config.json
3. RE-TEST    → python -m pytest test/ -q          (must stay green)
4. RE-BACKTEST→ python run_backtest_all.py
5. COMPARE    → build before/after table (see template below)
6. REPORT     → show table to user, ask: keep or revert?
7a. APPROVED  → append dated entry to docs/BACKTEST_LOG.md
                → update resources/doc/*.md if weights/thresholds moved
                → follow commit workflow
7b. REJECTED  → git checkout -- <files>  (revert)
                → do NOT touch BACKTEST_LOG.md
```

## Required report template

```markdown
## Before/After — <change description>

| Metric | Before | After | Δ |
|---|---|---|---|
| Trades | | | |
| Win rate | | | |
| Avg return/trade | | | |
| Expectancy | | | |
| Profit factor | | | |
| Avg MFE / Avg MAE | | | |
| Exit mix (target/trail/hold) | | | |

### Per-symbol
| Symbol | WR before | WR after | Sys% before | Sys% after |
|---|---|---|---|---|
...

Verdict: <improved / degraded / neutral> — keep or revert?
```

## Judgment rules

- Improvement = expectancy AND profit factor both non-worse, and no symbol
  catastrophically degraded (PF < 1 newly appearing counts as degradation).
- A win-rate-only improvement with worse expectancy is NOT an improvement.
- Small-sample noise: <5 trade difference per symbol → describe as "neutral".
