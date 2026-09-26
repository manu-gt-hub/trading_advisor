# Architecture

## What the system is

Daily-automated BUY/HOLD/SELL signal generator for US stocks. Runs via GitHub
Actions, writes to Google Drive sheets (Transactions / Buy Recommendations /
Analysis). Deterministic technical engine decides; optional GPT audit only vets
BUY signals.

## Module map

| File | Responsibility | Decision path? |
|---|---|---|
| `main.py` | Orchestrator: market-day guard, quotes, engine calls, filter pipeline, position/trailing mgmt | YES |
| `tools/technical_engine.py` | 3-layer scoring + regime classifier + signal. **SOLE DECIDER** | YES |
| `tools/custom_financial_calc.py` | Indicator computation → feature vector → delegates to engine | YES |
| `tools/risk_management.py` | ATR stop/target, R:R, sizing, correlation filter | YES |
| `tools/backtesting.py` | Historical signal simulation, MAE/MFE tracking | YES (the evaluator) |
| `tools/finnhub_client.py` | Finnhub quotes — US exchanges only on free plan | no |
| `tools/news_sentiment.py` | Earnings/news filter (Finnhub + GPT) | YES (pipeline filter) |
| `tools/llms.py` | GPT auditor (`audit_buy_signal`) + legacy helpers | partially (bounded adjustment) |
| `tools/google_handler.py` | Google Drive I/O, open positions, production trailing stop | YES (trailing logic) |
| `tools/historicals.py` | Alpha Vantage historical fetch | no |
| `tools/general.py` | Decision extraction, `action` column | partially |
| `resources/technical_config.json` | All numeric params, weights, regime rules | YES |
| `resources/symbols_markets.json` | symbol→exchange for TradingView URLs | no |
| `run_backtest_all.py` | Backtest entry point over `resources/historicals/*.csv` | validation |
| `docs/BACKTEST_LOG.md` | Engine quality baseline, dated entries | governance |

## Daily pipeline (production)

1. Market-day guard (weekends/US holidays → exit)
2. Fetch current prices (Finnhub)
3. Per symbol: load ~5y OHLCV → compute indicators → engine → signal+confidence+regime+sub_scores
4. If BUY and `LLM_AUDIT_ENABLED` → GPT audit (COHERENT ±adjust / INCOHERENT→HOLD)
5. Filter cascade: `MIN_BUY_CONFIDENCE` → open-position check → `MIN_RISK_REWARD_RATIO` → news → correlation dedup
6. Manage open positions: target hit → close win; stop hit → close loss; trailing stop (activate +2%, distance = original risk)
7. Persist 3 sheets to Google Drive

## Boundary rule (important)

`custom_financial_calc.py` computes numbers; `technical_engine.py` judges them.
Do not put scoring logic in the calculator or raw indicator math in the engine.
