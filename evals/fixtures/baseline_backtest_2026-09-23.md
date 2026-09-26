# FIXTURE: Consolidated baseline (step_days=5, target 10%, max_hold 30)

Snapshot of `run_backtest_all.py` consolidated output — 2026-09-23 baseline.
Use to verify agent-reported numbers are real, not fabricated.

## Consolidated (66 trades)

| Metric | Value |
|---|---|
| Total BUY signals | 66 |
| Wins | 23 |
| Win rate | 34.8% |
| Avg return/trade | +3.61% |
| Expectancy | −0.36% |
| Profit factor | 3.10 |
| Avg MFE | +6.72% |
| Avg MAE | −3.82% |

## Per-symbol

| Symbol | BUYs | Wins | Win% | AvgRet | PF | System% |
|---|---|---|---|---|---|---|
| MSFT | 11 | 3 | 27.3% | +2.89% | 3.41 | +34.32% |
| AAPL | 11 | 1 | 9.1% | −2.22% | 0.53 | −25.01% |
| NVDA | 18 | 10 | 55.6% | +6.86% | 8.82 | +216.35% |
| KO | 5 | 2 | 40.0% | +3.94% | 5.53 | +20.45% |
| META | 12 | 6 | 50.0% | +6.26% | 5.64 | +99.87% |
| V | 9 | 1 | 11.1% | +1.41% | 2.07 | +12.17% |

## Target-sweep reference (same data, different take-profit)

| Target | Trades | Win% | AvgRet | PF | Expectancy |
|---|---|---|---|---|---|
| 5% | 83 | 59.0% | +2.62% | 2.68 | +1.41% |
| 6% | 78 | 52.6% | +2.80% | 2.63 | +0.95% |
| 8% | 72 | 41.7% | +3.66% | 3.40 | +0.75% |
| 10% | 66 | 34.8% | +3.61% | 3.10 | −0.36% |
