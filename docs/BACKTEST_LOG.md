# Backtest Results Log

This file tracks backtest results over time as the prediction engine evolves.
Each entry records the configuration, changes made, and resulting metrics so
that future tuning has a documented baseline to compare against.

---

## 2026-09-22 — Engine rebalance + trailing stop + divergence/candlestick fixes

### Changes made

1. **Trend/momentum rebalance** — Swapped layer weights from trend=0.55/momentum=0.45
   to trend=0.45/momentum=0.55. Rationale: the system targets 1-4 week trades where
   momentum matters more than slow moving-average structure.

2. **Weekly confirmation weight reduced** — From 0.20 to 0.10 in the trend layer.
   Weekly MA(10w) vs MA(30w) is largely redundant with daily SMA50/SMA200 (sma_cross),
   so it was receiving disproportionate weight for near-duplicate information.

3. **Bearish divergence: swing-high detection** — Replaced block-max comparison
   (max of last 14 bars vs previous 14 bars) with actual swing-pivot detection
   (local maxima with order=5). Reduces false positives in consolidation phases.

4. **Candlestick patterns: context-aware scoring** — Bullish patterns below SMA50
   (pullback) score 1.0; at highs score 0.5. Bearish patterns above SMA50 score -1.0;
   below score -0.5. Conflicting bull+bear patterns cancel to 0.0 instead of
   silently dropping the bearish signal.

5. **BUY threshold unified** — Python `DEFAULT_BUY_THRESHOLD` aligned to 0.5
   (same as JSON config) to eliminate the confusing dual-default.

6. **`MIN_RISK_REWARD_RATIO` externalized** — Previously hardcoded `min_rr = 1.2`
   in main.py, now driven by the `MIN_RISK_REWARD_RATIO` environment variable
   (default 1.2).

7. **Trailing stop in production** — `google_handler.update_transactions` now tracks
   `highest_price` per open position and ratchets `stop_loss` upward once the position
   is in profit by >= 2%. Trail distance equals the original risk (buy_value - initial
   stop_loss). Previously only the backtest had a trailing stop; production used a
   fixed stop.

### Backtest configuration

- **Data**: 5 years of daily OHLCV (2021-05 to 2026-05), 7 symbols
- **Target profit**: 10%
- **Max holding period**: 30 trading days
- **Step**: evaluate every 10 days
- **S&P 500 context**: mocked as NEUTRAL (not a live feed in backtest)
- **Valuation metrics**: disabled (SSL failure in local env; no impact on engine decision)
- **Weekly confirmation**: mocked as None (insufficient weekly history in some CSVs)

### Results comparison

#### Before (baseline, 2026-09-22 pre-changes)

```
Symbol   BUYs  Wins   Win%   AvgRet%  System%    B&H%     vs B&H
MSFT       10     2   20.0%   +1.88%  +18.85%   +90.36%   -71.51%
AAPL        7     0    0.0%   -0.97%   -7.51%   +71.19%   -78.71%
NVDA       13     7   53.8%   +4.63%  +73.30%  +903.18%  -829.88%
KO          5     1   20.0%   +0.32%   +0.75%   +18.72%   -17.96%
META       11     5   45.5%   +3.05%  +31.15%  +195.90%  -164.74%
V           7     0    0.0%   +1.62%  +11.83%   +48.66%   -36.83%
TOTAL      53    15   28.3%   +2.24%
```

#### After (post-changes)

```
Symbol   BUYs  Wins   Win%   AvgRet%  System%    B&H%     vs B&H
MSFT        8     2   25.0%   +2.51%  +20.39%   +90.36%   -69.97%
AAPL        6     0    0.0%   +0.86%   +4.40%   +71.19%   -66.79%
NVDA       14     8   57.1%   +5.06%  +91.83%  +903.18%  -811.36%
KO          4     1   25.0%   +2.21%   +8.60%   +18.72%   -10.12%
META        9     5   55.6%   +4.57%  +41.51%  +195.90%  -154.38%
V           6     0    0.0%   +1.77%  +10.98%   +48.66%   -37.68%
TOTAL      47    16   34.0%   +3.33%
```

#### Delta

| Metric             | Before | After  | Change    |
|--------------------|--------|--------|-----------|
| Total BUY signals  | 53     | 47     | -6        |
| Win rate           | 28.3%  | 34.0%  | **+5.7pp**|
| Avg return/trade   | +2.24% | +3.33% | **+1.09pp**|
| AAPL system return | -7.51% | +4.40% | +11.91pp  |
| KO system return   | +0.75% | +8.60% | +7.85pp   |
| NVDA system return | +73.30%| +91.83%| +18.53pp  |
| META system return | +31.15%| +41.51%| +10.36pp  |

### Detailed diagnostics (post-changes)

#### Confidence calibration

```
Confidence   Trades  Win rate  Avg return
0.3-0.5          1      0.0%     +2.40%
0.5-0.6         24     33.3%     +3.64%
0.6-0.7         12     33.3%     +1.25%
0.7-1.0         10     40.0%     +5.20%
```

Note: confidence band 0.6-0.7 underperforms 0.5-0.6. Calibration is inverted
in the mid-range. Only 0.7+ shows clear improvement.

#### Exit reason breakdown

```
Reason           Trades  Avg return  Median  Avg days
target               16    +11.55%  +11.15%      14d
trailing_stop         14     -1.65%   -1.75%      18d
max_hold              17     -0.30%   +2.88%      30d
```

Trailing stop is the largest source of losses. 60% of losing trades were +2%
or more at some point before turning negative.

#### Per-symbol quality

```
Symbol    N   Win%   AvgRet  AvgConf  AvgDays  Leakage
AAPL      6    0.0%  +0.86%   0.55      25d    3.67pp
KO        4   25.0%  +2.21%   0.59      25d    2.23pp
META      9   55.6%  +4.57%   0.66      19d    3.90pp
MSFT      8   25.0%  +2.51%   0.66      24d    3.49pp
NVDA     14   57.1%  +5.06%   0.62      14d    3.45pp
V         6    0.0%  +1.77%   0.58      28d    2.11pp
```

### Known remaining issues

1. **10% target is unreachable for low-volatility stocks** (AAPL, V, KO) within
   30 days. An ATR-adaptive target would improve win rates for these symbols.

2. **Trailing stop too tight** — 2.5x ATR after +2% gets stopped out by normal
   intraday noise. Consider 3.5x ATR with +4% activation.

3. **No technical exit signal for open positions** — If regime shifts to
   DISTRIBUTION or TRENDING_DOWN while holding, the system does not close.
   It waits for target or stop, potentially riding losses down.

4. **Confidence not well-calibrated in the 0.6-0.7 range** — mid-confidence
   signals underperform low-confidence ones. The scoring formula may need
   recalibration, or the risk penalty factor (0.5) may be compressing the
   useful range.

---

## 2026-10-31 — Backtest aligned with the production pipeline (new baseline)

Measurement change, not a strategy change: production signals and exits are
unchanged. The backtester now replays the production pipeline, so results are
**not comparable** with earlier entries.

### What changed in the simulation

| | Before | Now (= production) |
|---|---|---|
| Evaluation frequency | every 5 days | daily (`step_days=1`) |
| Initial stop-loss (2×ATR) | not simulated | yes |
| Trailing stop | 2.5×ATR from max close | `risk_management.update_open_position` (same function production runs) |
| Target exit price | close of the day | target price (as recorded in the Sheet) |
| Time exit | 30 days | none (`open_at_end` if data ends) |
| R:R + confidence filters | no | yes (`MIN_RISK_REWARD_RATIO`, `MIN_BUY_CONFIDENCE`) |
| Weekly confirmation | mocked off | on |
| Valuation (yfinance) | network call per step | neutral (no point-in-time data) |
| Expectancy formula | mixed win definitions (bug) | consistent (= avg return) |

Not replayable offline: LLM audit, news/earnings, correlation filter, valuation, real S&P500 (mocked NEUTRAL).

Parameters: target 10%, min_buy_confidence 0.5, min_risk_reward_ratio 1.2, min_history 250, step_days 1.

### Consolidated

| Metric | Old simulation | Aligned |
|---|---|---|
| Trades | 66 | 93 |
| Target hit rate | 34.8% | 22.6% |
| Avg return = expectancy | +3.61% (logged as −0.36%) | **+2.08%** |
| Profit factor | 3.10 | **2.88** |
| Avg MFE / MAE | +6.72% / −3.82% | +5.11% / −2.30% |

### Per symbol (aligned)

```
Symbol  BUYs Wins   Win%  AvgRet    PF  System%    B&H%
MSFT      19    4  21.1%  +1.83%  2.54  +38.10%  +90.36%
AAPL      13    2  15.4%  +0.92%  1.74  +11.18%  +71.19%
NVDA      20    4  20.0%  +3.58% 42.59  +99.12% +903.18%
KO         8    2  25.0%  +1.41%  1.96  +10.67%  +18.72%
META      21    6  28.6%  +1.87%  2.09  +42.44% +195.90%
V         12    3  25.0%  +2.08%  2.67  +26.02%  +48.66%
AMZN       0    -      -       -     -        -   -0.94%
```

### Exit reasons

```
Reason         Trades  AvgRet
target             21  +10.00%
trailing_stop      47   +1.79%
stop_loss          25   -4.00%
```

### Open experiments (not applied)

- Stop fill at market price (`min(stop, price)`) instead of the stop price: avg return +1.24%, PF 1.80. More honest measurement; candidate next baseline.
- Trailing distance fixed at the initial risk (today it uses `buy_value − current stop`, which freezes the stop near breakeven): avg return +2.26%, target hit 33%, PF 2.52. Mixed; re-test on the honest baseline.

---

## 2026-11-03 — Out-of-sample split added to the report (baseline OOS figures)

Reporting change only: trades and consolidated metrics are identical to the
2026-10-31 baseline (93 trades, +2.08%, PF 2.88). The runner now also splits
trades by entry date at `backtest.oos_start = 2025-01-01`.

**From now on:** tune on IN-SAMPLE; accept a change only if OUT-OF-SAMPLE
does not degrade. Caveat: the current config was tuned on the full history,
so these OOS figures are optimistic, not a clean holdout.

| Period | Trades | Win% | AvgRet | PF | AvgMAE |
|---|---|---|---|---|---|
| In-sample (< 2025-01-01) | 72 | 22.2% | +2.21% | 3.17 | -2.12% |
| **Out-of-sample (≥ 2025-01-01)** | **21** | 23.8% | **+1.64%** | **2.16** | -2.91% |

Per year: 2023 +2.41% (36) · 2024 +2.08% (30) · 2025 +1.10% (17) · 2026 +3.91% (4).
2022 (bear market) produced a single trade: the regime gate kept the system out.

Per symbol avg return IN → OUT: AAPL +1.19 → +0.31 · NVDA +3.84 → +2.78 ·
KO +0.58 → +2.81 · META +2.16 → +0.63 · V +2.37 → +1.67 · MSFT has no OOS
trades (its CSV ends 2025-05) — refreshing MSFT data is pending.

---

## 2026-11-11 — P/B adjustment off, price in the label (baseline unchanged) + rejected ATR exit target

**Baseline unchanged.** The backtest always ran with a neutral valuation (no
point-in-time fundamentals) and the label is display only, so trades are
identical. Re-run on this code: 22 symbols (`backtest.universe`), data
2021-11 → 2026-11, real point-in-time S&P500 context. This is the first logged
run of the 22-symbol universe and the current reference:

| Period | Trades | Win% | AvgRet | PF | AvgMFE | AvgMAE |
|---|---|---|---|---|---|---|
| In-sample (< 2025-01-01) | 191 | 16.8% | +1.55% | 2.32 | +4.57% | -2.33% |
| **Out-of-sample (≥ 2025-01-01)** | **159** | 14.5% | **+1.33%** | **2.12** | +4.20% | -2.41% |
| All | 350 | 15.7% | +1.45% | 2.23 | +4.40% | -2.37% |

Exit reasons: target 55 (+10.00%) · trailing stop 193 (+1.88%) · stop loss 98
(-4.09%) · open at end 4. Per year: 2022 -1.14% (5) · 2023 +1.51% (86) ·
2024 +1.71% (100) · 2025 +1.55% (75) · 2026 +1.14% (84).

### Changes

- **P/B valuation adjustment off** (`valuation.apply_adjustment=false`). It
  added -0.05…+0.07 to confidence in production only and was never backtested;
  with `MIN_BUY_CONFIDENCE=0.5` its only effect was to drop BUYs of high P/B
  names. P/B is still reported. Production may now emit a few more BUYs on high
  P/B names; this cannot be measured offline.
- **`Current_Price` added** to the `manual_financial_analysis` label.

### Rejected: sell at the ATR take-profit instead of the fixed 10%

Hypothesis: exits use the fixed 10% target while R:R and the sheet use
min(10%, 3×ATR), so low-volatility names rarely reach their target. Tested by
selling at min(10%, 3×ATR):

| | Trades | Target hit | AvgRet | PF | OOS AvgRet | OOS PF |
|---|---|---|---|---|---|---|
| Baseline (10% fixed) | 350 | 15.7% | +1.45% | 2.23 | +1.33% | 2.12 |
| ATR target | 414 | 25.8% | +1.13% | 1.95 | +1.02% | 1.84 |

More targets hit but winners are cut (+5.84% vs +10.00% per target exit) and
more trades end at the stop (122 vs 98). Out-of-sample degrades → not applied;
the existing regression tests that keep the 10% target are right.
