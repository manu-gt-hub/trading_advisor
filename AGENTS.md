# AGENTS.md — Instructions for AI coding agents (Claude, GPT, Devin, Cursor, etc.)

This file is the **harness contract** for any LLM/agent working on this repository.
Read it fully before making changes. If your host also loads `CLAUDE.md` or similar
files, treat this file as the canonical source for workflow rules.

## Harness layout

```
AGENTS.md            # THIS FILE — overview + rules summary (read first)
CLAUDE.md            # pointer → AGENTS.md
.agent/
  instructions/      # static context: architecture.md, engine.md, commands.md, env_vars.md
  workflows/         # SOPs: engine_change.md, commit.md, new_parameter.md
  policies/          # hard rules: backtest_policy.md, commit_policy.md, secrets_policy.md
evals/
  tasks/             # task prompts for evaluating agent compliance
  fixtures/          # frozen baselines (expected backtest metrics)
  rubrics/           # scoring checklists (engine_change_rubric.md, commit_rubric.md)
  run/               # verify_invariants.py — automated compliance checks
```

The `.agent/` modules contain the full detail of each rule summarized here —
when in doubt, the **policies/** files are authoritative. `evals/` is used to
grade whether an agent actually followed the rules.

---

## 1. What this project is

**Trading Advisor** — an automated stock BUY/HOLD/SELL signal generator that runs
daily via GitHub Actions and writes results to Google Drive spreadsheets.

**Core principle (non-negotiable):**

> **The technical engine decides. The LLM only audits.**

A deterministic, config-driven layered engine produces every signal. An optional GPT
audit may veto a BUY (BUY → HOLD) or apply a bounded confidence adjustment
`[-0.3, +0.1]` — it can never create or reclassify signals.

## 2. Architecture map

```
main.py                          # Orchestrator: market-day guard, prices, engine calls,
                                 # filter pipeline, position/trailing-stop management
tools/technical_engine.py        # SOLE DECIDER: 3-layer engine + regime classifier
tools/custom_financial_calc.py   # Indicator computation → feature vector → engine
tools/finnhub_client.py          # Finnhub quotes (free plan = US exchanges only)
tools/risk_management.py         # ATR stop-loss/take-profit, R:R, sizing, correlation,
                                 # update_open_position (exit rules shared with backtest)
tools/llms.py                    # LLM auditor (audit_buy_signal)
tools/llm_client.py              # Provider-neutral LLM call (LLM_PROVIDER: openai | anthropic)
tools/news_sentiment.py          # Earnings/news filter (Finnhub + GPT)
tools/backtesting.py             # Backtester: simulates signals, tracks MAE/MFE per trade
tools/google_handler.py          # Google Drive I/O, open-position tracking, trailing stop
tools/historicals.py             # Yahoo history (Alpha Vantage fallback), live benchmark closes
tools/shadow_signals.py          # Shadow mode: logged-only candidate signals (never decide)
tools/general.py                 # 'action' column, NYSE calendar, TLS + log-redaction helpers

resources/technical_config.json  # ALL indicator params, weights, regime rules, thresholds
resources/symbols_markets.json   # symbol → exchange map (for TradingView URLs)
resources/historicals/           # <SYMBOL>.csv per universe symbol + market/ (GSPC, VIX, SPY, sector ETFs)
download_historicals.py          # Refresh the backtest data set from Yahoo Finance (free)
resources/doc/*.md               # Detailed engine documentation (index in resources/doc/README.md)
docs/ARCHITECTURE.md             # System architecture: services, daily run, filters, position lifecycle, backtest parity

run_backtest_all.py              # Runs the backtest over backtest.universe (ENTRY POINT for validation)
evals/run/analyze_shadow.py      # Judges shadow signals against realised forward returns
docs/BACKTEST_LOG.md             # Single source of truth for engine quality (dated sections)
test/test_*.py                   # pytest suite (offline; conftest blocks yfinance)
```

### Engine summary (what the signals mean)

- **Layer 1 — Trend** `[-1,1]`: SMA50/200, price vs SMA200/EMA20/SMA50, MA50 slope, ADX (+DI/-DI).
- **Layer 2 — Momentum** `[-1,1]`: RSI + MACD (primary); Stochastic RSI + ROC (secondary).
- **Layer 3 — Risk** `[0,1]`: volatility, OBV/volume divergences, overbought exhaustion.
- **Regime**: `TRENDING_UP / TRENDING_DOWN / RANGE / DISTRIBUTION` (SMA + ADX). BUY **only** in `TRENDING_UP`.
- **Aggregation**: `directional = 0.45·trend + 0.55·momentum`, then `confidence = directional · (1 − 0.5·risk)`.
- Then a filter pipeline: `MIN_BUY_CONFIDENCE` → open-position check → `MIN_RISK_REWARD_RATIO` (ATR-based) → news filter → correlation dedup.
- Exits (`risk_management.update_open_position`, shared by production and backtest):
  take-profit at `REVENUE_PERCENTAGE`, initial stop 2×ATR, trailing stop (activates
  at +2%, distance = buy_value − current stop). No time exit.
- The backtest replays the same pipeline daily (engine → confidence → open-position
  → R:R → exits). Not replayable offline: LLM audit, news, correlation, valuation.

**Everything numeric lives in `resources/technical_config.json`.** If you change a
threshold/weight, the logic adapts automatically — it is config-driven.

## 3. MANDATORY workflow rules

### Rule 1 — Never commit engine changes without a backtest comparison

Any change to the **prediction/decision path** — i.e. anything in
`technical_engine.py`, `custom_financial_calc.py`, `risk_management.py`,
`main.py` filter logic, or `resources/technical_config.json` (weights, thresholds,
regime rules, stop/trailing parameters) — **must** follow this procedure:

1. **Before the change**: run `python run_backtest_all.py` and record the metrics
   (or diff against the latest `docs/BACKTEST_LOG.md` baseline entry).
2. **After the change**: run `python run_backtest_all.py` again.
3. **Compare** before vs after: win rate, avg return/trade, expectancy,
   profit factor, exit-reason mix, MAE/MFE, and per-symbol breakdown —
   **in-sample and out-of-sample** (split at `backtest.oos_start`). Tune on
   in-sample only; a change that degrades out-of-sample is reverted.
4. **Report to the user** a clear before-vs-after table. Ask explicitly:
   keep or revert?
5. Only on **user approval**: commit the change AND append a new dated entry to
   `docs/BACKTEST_LOG.md` (the file becomes the new baseline).
6. On **rejection**: revert the code. Do not update `BACKTEST_LOG.md`, do not commit.

> A change that "looks better in theory" but degrades backtest expectancy/profit
> factor gets reverted. Data decides, not intuition. (This already happened once:
> relaxing the trailing stop to 3.5×ATR/+4% looked sensible but degraded
> expectancy −0.52pp and profit factor −0.39 — it was reverted.)

**Non-engine changes** (bug fixes, I/O, formatting, docs, tests) do not need a
backtest comparison — but must pass the test suite.

### Rule 2 — Tests must pass before committing

```bash
python -m pytest test/ -q
```

All tests must pass. If you changed behavior, update or add tests. If a test
fails because behavior intentionally changed, update the test AND note it in your
report to the user.

### Rule 3 — Confirm before committing (unless auto-commit was authorized)

Before any `git commit` or `git push`, **always**:

1. Present the user a summary of the pending changes: files touched, what changed
   and why, plus test/backtest status.
2. Propose the commit message.
3. Wait for explicit user confirmation ("commit it", "yes", etc.).

This applies to **all** changes — docs, config, tests, engine code — not only
engine changes. Never commit silently, never batch a commit into a larger
approved action without listing it, never commit secrets, API keys, credentials,
or `.env` files. Pushing also requires its own explicit approval.

**Exception**: if the user explicitly says when launching the task that the
agent may commit automatically ("hazlo y commitea", "implement and commit"),
the agent may commit directly as part of the task — and should report what it
committed afterwards. The authorization is per-task and does not carry over.

### Rule 4 — Keep `docs/BACKTEST_LOG.md` honest

- One entry per approved engine change: `## YYYY-MM-DD — description`.
- Include: what changed, before/after metric table, per-symbol table, diagnostics.
- Single file, appended at the end — do not create per-date files.
- The **latest entry is the baseline** for the next comparison.

### Rule 5 — Config over code

Prefer changing `resources/technical_config.json` over hardcoding values. If you
add a tunable parameter, expose it in the JSON (and/or env var if deployment-time)
rather than embedding a literal in Python. If weights/thresholds change
significantly, also update `resources/doc/*.md`.

## 4. Commands

```bash
# Install (runtime + pytest)
pip install -r requirements-dev.txt

# Full test suite
python -m pytest test/ -q

# Engine validation backtest (fully offline; replays the production pipeline)
python run_backtest_all.py

# Production run (requires env vars below)
python main.py
```

## 5. Environment variables (production)

| Variable | Purpose |
|---|---|
| `SYMBOLS_INTEREST_LIST` | Python-list literal of tickers (US exchanges only for Finnhub free) |
| `FINNHUB_API_KEY` | Quotes + news (free tier: NYSE/NASDAQ only, no `.L`/`.DE`/`.PA`) |
| `LLM_PROVIDER`, `MODEL_NAME` | LLM backend (`openai` default, or `anthropic`) and model for the BUY audit + news sentiment; defaults in `llm.default_models` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Key of the selected provider (all LLM calls go through `tools/llm_client.py`) |
| `GDRIVE_FILE_ID`, `BUY_RECOMMENDATIONS_ID`, `ANALYSIS_FILE_ID`, `GDRIVE_CREDENTIALS_JSON` | Google Drive I/O |
| `REVENUE_PERCENTAGE` | Take-profit target % (e.g. `10`) |
| `MIN_BUY_CONFIDENCE` | Min confidence for BUY (engine + post-audit filter; backtest reads it too) |
| `MIN_RISK_REWARD_RATIO` | Min R:R for BUY (default 1.2) |
| `LLM_AUDIT_ENABLED` | `true`/`false` — GPT audit of BUY signals |
| `NEWS_SENT_ANALYSIS` | `true`/`false` — news/earnings filter |
| `FORCE_OPINION` | `DEFAULT` / `CUSTOM` (legacy `LLM1`/`LLM2` fall back to `DEFAULT`) |
| `ALPHA_API_KEY`, `ALPHA_VANTAGE_URL` | Historical data refresh |
| `LOG_LEVEL`, `DISABLE_SSL_VERIFY` | Ops |
| `ENGINE_CONFIG_OVERRIDES` | JSON `{"dotted.path": value}` overriding any `technical_config.json` value at runtime. **Changing an engine value this way is an engine change (Rule 1)** |
| `SHADOW_MODE_ENABLED`, `SHADOW_LOG_FILE_ID` | Shadow mode switch and the sheet that accumulates its log |

Backtest (`run_backtest_all.py`) works fully offline from `resources/historicals/*.csv`.

## 6. Known limitations & pitfalls

- **Finnhub free plan = US exchanges only.** Symbols like `BA.L`, `ABB` (wrong
  ticker), `.DE`, `.PA` will 403/return zeros. The system skips them safely.
- **Low-volatility / defensive names are weak under the current config**: a fixed
  10% target is rarely reached (MCD, PG, HD, UNH, LIN lose; AAPL, KO, V are thin).
  Per-symbol results differ a lot — always check the per-symbol table, not just
  the consolidated row.
- **The backtest universe is fixed by criteria, not by results** (22 symbols,
  `backtest.universe`). Never drop or add symbols because of how the system did
  on them; any change to the universe or the data changes the baseline.
- **Backtest ≠ production in a few known places**: no LLM audit, news filter,
  correlation filter, valuation adjustment or shadow signals. S&P500 trend, VIX
  and relative-strength benchmarks are replayed point-in-time from
  `resources/historicals/market/`. Everything else is the same code path.
- **Candidate factors have weight 0** (`rs_market`, `rs_sector`, `overextension`,
  `vix`). Tested on 2026-11-09 (one change each, 17 symbols): none
  improved the backtest enough to be adopted, so all stay at weight 0. They are computed and logged but do not affect scores. Give them weight
  only through the backtest procedure — a weight 0 → non-zero change is an engine
  change.
- **Shadow mode must never influence a decision.** Do not read `shadow_*`
  columns in the decision path; promote a signal into the engine instead.
- **Look-ahead bias**: the backtester slices history per evaluation day. If you
  modify `backtesting.py`, preserve the `min_history`-gated windowing.
- **Exit logic lives in one place**: change `risk_management.update_open_position`,
  never re-implement exits in `backtesting.py`. New backtest exit reasons go in
  `backtesting.EXIT_REASONS` (the report iterates it).
- **Backtest log entries before 2026-10-31** used a different simulation (step 5,
  30-day max hold, 2.5×ATR trailing, no initial stop, inconsistent expectancy
  formula). Compare only against entries produced by the aligned backtest.
- **Trailing stop is a delicate knob**: both directions (tighter/looser) have been
  tried and reverted. Treat changes as experiments requiring Rule-1 validation.

## 7. Style & conventions

- Python 3, `pandas`, plain functions + dataclasses — no framework.
- Comments are sparse; keep code compact and idiomatic. Don't add comments unless asked.
- Indicator math lives in `custom_financial_calc.py`; scoring/decisions live in
  `technical_engine.py` — respect the boundary (calculation vs judgment).
- User-facing docs and the user communicate in Spanish; code identifiers and
  inline docs stay in English.
- New config/parameters go in `resources/technical_config.json` with a sane
  default so existing deployments don't break.

## 8. Definition of done for an engine change

- [ ] Backtest run before the change (baseline recorded)
- [ ] Backtest run after the change
- [ ] Before/after table reported to the user
- [ ] User approved or reverted (no silent commits)
- [ ] `pytest` green
- [ ] `docs/BACKTEST_LOG.md` updated (if approved)
- [ ] `resources/doc/*.md` updated (if weights/thresholds changed significantly)
- [ ] Change summary + proposed commit message shown to user; commit only after explicit confirmation (or per-task auto-commit authorization — then report what was committed)
