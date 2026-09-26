# The engine — what you must know before touching it

## Layers

| Layer | Range | Inputs | Weight |
|---|---|---|---|
| 1 — Trend | [-1, 1] | SMA50/200 cross, price vs SMA200/EMA20/SMA50, MA50 slope, ADX +DI/−DI | 0.45 |
| 2 — Momentum | [-1, 1] | RSI + MACD (primary); Stoch RSI + ROC (secondary) | 0.55 |
| 3 — Risk | [0, 1] | 20d volatility, OBV/volume divergence, overbought exhaustion | penalty |

```
directional = 0.45 * trend_score + 0.55 * momentum_score
confidence  = directional * (1 - 0.5 * risk_score)
```

## Regime gate

SMA50 vs SMA200 + ADX → `TRENDING_UP / TRENDING_DOWN / RANGE / DISTRIBUTION`.
**BUY is only emitted in `TRENDING_UP`** regardless of scores.

## Exit mechanics

- Take-profit: `REVENUE_PERCENTAGE`, capped at 3×ATR.
- Stop-loss: 2×ATR below entry.
- Trailing stop: activates at +2% gain; distance = original risk (entry − initial stop). **Never moves down.**
- Backtest adds `max_hold` exit at 30 days.

## Config-driven

Every number above lives in `resources/technical_config.json`. Change the JSON,
not the code, when tuning. If you add a new tunable, give it a safe default so
deployments without it don't break.

## Known sensitivities (learned the hard way)

- Trailing stop: loosening (3.5×ATR/+4%) degraded expectancy −0.52pp and PF −0.39
  → reverted. Tightening also hurts (kills +4.99% MFE trades at −1.59%).
- `step_days=5` doubles signals vs 10 but adds mediocre entries — expected, not a bug.
- Confidence band 0.6–0.7 underperforms 0.5–0.6 — calibration issue, not fixed.
- AAPL/V underperform: low volatility can't reach 10% target in 30 days.
  Target-sweep analysis: 8% maximizes global PF (3.40) and avg return (+3.66%).

## LLM boundary

GPT never creates signals. Only audits BUY: `COHERENT` → adjust confidence
`[-0.3, +0.1]`; `INCOHERENT` → veto to HOLD. Do not expand its authority.
