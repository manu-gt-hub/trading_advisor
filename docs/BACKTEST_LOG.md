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
