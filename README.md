# Trading Advisor

Automated stock trading signal generator driven by a **deterministic layered technical engine**. The technical system is the **sole decision maker**; the LLM (GPT) only **audits** BUY signals. Runs daily via GitHub Actions and saves results to Google Drive.

## 🚀 Features

### Decision Engine
- **Technical engine decides** — A deterministic, config-driven engine (`technical_engine.py`) produces every BUY/HOLD/SELL signal. No LLM in the classification path.
- **LLM as auditor only** — GPT is invoked **only when the technical signal is BUY**. It cannot re-classify; it may only (1) flag **INCOHERENT** setups (downgrading BUY→HOLD) and (2) apply a small **bounded confidence adjustment** (`[-0.3, +0.1]`).
- **Three layers, clear hierarchy** — `trend`, `momentum`, and `risk` are computed independently, normalized to a common scale, and aggregated into explicit **sub-scores** (`trend_score`, `momentum_score`, `risk_score`).
- **Explicit regime classifier** — `TRENDING_UP`, `TRENDING_DOWN`, `RANGE`, `DISTRIBUTION` based on **SMA(50/200) + ADX** (+DI/-DI). BUY is only allowed in `TRENDING_UP`.
- **Structured, deterministic output** — `signal + strength + regime + sub_scores`, no narrative text.
- **Indicators & weights in JSON** — All indicators, weights, regime rules and thresholds live in `resources/technical_config.json`.
- **Modes** via `FORCE_OPINION`: `DEFAULT` (technical decides, LLM audits BUY), `CUSTOM` (technical only), `LLM1`/`LLM2` (legacy GPT-only override).
- **MIN_BUY_CONFIDENCE** — Minimum (audited) technical confidence to accept a BUY (0.0-1.0, default 0.6).
- **Risk/Reward filter** — Blocks BUY signals with R:R ratio < 1.5 (ATR-based stop-loss vs take-profit).
- **News sentiment filter** — Blocks BUY signals when upcoming earnings or strongly negative news detected (Finnhub + GPT).
- **Position tracking** — Skips BUY if symbol already has an open (unsold) position.
- **Adaptive take-profit** — Uses the more conservative of fixed REVENUE_PERCENTAGE and 3×ATR.
- **Market day guard** — Skips execution on weekends and US holidays to avoid stale prices.
- **LLM cost optimization** — Only calls GPT to audit BUY candidates; SELL/HOLD signals skip the LLM entirely.

### Technical Analysis (layered, `technical_engine.py` + `custom_financial_calc.py`)
- **Layer 1 — Trend** `[-1, 1]`: SMA 50/200 cross, price vs SMA200, price vs EMA20/SMA50, MA50 slope, ADX direction (+DI/-DI).
- **Layer 2 — Momentum** `[-1, 1]`: **RSI + MACD (primary)**, Stochastic RSI + ROC (secondary, lower weight).
- **Layer 3 — Risk** `[0, 1]`: historical volatility, **volume confirmation / OBV divergence**, overbought exhaustion, **bearish divergences**. Volume and divergences are risk factors, not momentum.
- **Regime classifier**: SMA + ADX → `TRENDING_UP` / `TRENDING_DOWN` / `RANGE` / `DISTRIBUTION`.
- **Aggregation**: `directional = w_trend·trend_score + w_momentum·momentum_score`, then risk-penalized; regime gates the final signal.
- **Supporting indicators** (reported but not in the core score): Bollinger Bands, ATR 14, Fibonacci retracements, candlestick patterns, weekly confirmation, S&P500 context.

### Risk Management (`risk_management.py`)
- **Stop-loss**: ATR-based (2x ATR below entry)
- **Take-profit**: Revenue percentage target or 3x ATR
- **Position sizing**: Fixed-risk model with 20% portfolio cap per position
- **Diversification**: Correlation filter removes highly correlated BUY signals (Pearson > 0.75)
- **Risk/Reward ratio**: Computed for every signal

### Backtesting (`backtesting.py`)
- Simulates signals over historical data **without look-ahead bias**
- Measures win rate, average return, max drawdown per trade
- Multi-stock backtest results (10% target, 30-day hold, 5 years):
  - **NVDA**: 58.8% win rate, +10.43% avg return
  - **META**: 47.9% win rate, +7.04% avg return
  - **MSFT**: 24.4% win rate, +2.21% avg return
  - System works best on volatile tech stocks
- Run all backtests: `python run_backtest_all.py`
- Normalize CSV formats: `python normalize_csvs.py`

### Infrastructure
- **Daily execution** via GitHub Actions (scheduled cron)
- **Google Drive** integration for persisting analysis and recommendations
- **93 tests**, fully mocked (no external API calls), ~12s execution

## 🛠️ Getting Started

### Prerequisites

- Python 3.11+
- API keys: OpenAI, Finnhub, Alpha Vantage
- Google Drive service account credentials

### Installation

```bash
git clone https://github.com/manu-gt-hub/trading_advisor.git
cd trading_advisor
pip install -r requirements.txt
```

### Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `GPT_MODEL_NAME` | GPT model (e.g., `gpt-4o`) |
| `FINNHUB_API_KEY` | Finnhub API key |
| `ALPHA_API_KEY` | Alpha Vantage API key |
| `ALPHA_VANTAGE_URL` | Alpha Vantage base URL |
| `GDRIVE_CREDENTIALS_JSON` | Google Drive service account JSON |
| `GDRIVE_FILE_ID` | Transactions sheet ID |
| `BUY_RECOMMENDATIONS_ID` | Buy recommendations sheet ID |
| `ANALYSIS_FILE_ID` | Full analysis sheet ID |
| `SYMBOLS_INTEREST_LIST` | Python list of tickers, e.g. `"['AAPL','MSFT']"` |
| `REVENUE_PERCENTAGE` | Target profit % for take-profit (e.g., `10`) |
| `FORCE_OPINION` | Decision mode: `DEFAULT`, `LLM1`, `LLM2`, `CUSTOM` |
| `MIN_BUY_CONFIDENCE` | Single BUY threshold (0.0-1.0, default 0.6): the engine emits BUY only when the risk-adjusted score reaches it, and BUYs are also accepted post-audit against the same value |
| `LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`) |
| `TRANSACTIONS_MAX_RECORDS` | Max rows in transactions sheet (default 100) |
| `NEWS_SENT_ANALYSIS` | Enable news sentiment filter (`true`/`false`, default `false`) |

### Usage

1. Set environment variables (`.env` file or GitHub Actions secrets)
2. Add symbols to `SYMBOLS_INTEREST_LIST`
3. Add market mapping in `resources/symbols_markets.json`
4. Run: `python main.py` (or `python main.py --test` for debug output)

### Google Drive Output

| Sheet | Columns |
|---|---|
| **Analysis** | symbol, current_price, llm_opinion, llm_confidence, manual_financial_analysis, technical_confidence, stop_loss, take_profit, risk_reward_ratio, action |
| **Buy Recommendations** | Same + buy_date, tradingview_url |

## 🧪 Tests

```bash
# Run all tests (excludes Google Drive integration tests)
pytest test/ -v --ignore=test/test_google_handler.py

# Run with output visible
pytest test/ -v -s --ignore=test/test_google_handler.py

# Run only backtesting tests
pytest test/test_backtesting.py -v -s

# Run E2E (requires all API keys)
python main.py --test
```

All tests are mocked — no external API calls. Google Drive tests (`test_google_handler.py`) are integration tests excluded by default.

## � Signal Pipeline

```mermaid
flowchart TD
    Z{Market day?} -->|weekend/holiday| X0[Skip execution]
    Z -->|weekday| A[Fetch quotes - Finnhub]
    A -->|current prices| B[Layered technical engine<br>trend/momentum/risk + regime]
    B -->|SELL/HOLD| S[LLM skipped<br>technical decides]
    B -->|BUY signal| D[LLM AUDIT<br>coherence + bounded conf adj]
    D -->|INCOHERENT| X2[Downgraded to HOLD]
    D -->|COHERENT| C{MIN_BUY_CONFIDENCE<br>filter on audited conf}
    C -->|conf < threshold| X1[Discarded]
    C -->|conf >= threshold| P{Position<br>tracking}
    P -->|already holding| X6[Skip - open position]
    P -->|not holding| RR{Risk/Reward<br>ratio filter}
    RR -->|R:R < 1.5| X5[BUY blocked]
    RR -->|R:R >= 1.5| F{News sentiment<br>filter}
    F -->|earnings soon or<br>negative news| X3[BUY blocked]
    F -->|no risks| G{Correlation<br>filter}
    G -->|Pearson > 0.75| X4[Duplicate removed]
    G -->|uncorrelated| H[Google Drive<br>BUY recommendation]

    style X0 fill:#868e96,color:#fff
    style X1 fill:#ff6b6b,color:#fff
    style X2 fill:#ffa94d,color:#fff
    style X3 fill:#ff6b6b,color:#fff
    style X4 fill:#ffa94d,color:#fff
    style X5 fill:#ff6b6b,color:#fff
    style X6 fill:#ffa94d,color:#fff
    style S fill:#868e96,color:#fff
    style H fill:#51cf66,color:#fff
```

## �� Architecture

```
main.py                          # Entry point: orchestrates analysis pipeline
tools/
  technical_engine.py            # Layered deterministic engine (trend/momentum/risk) + regime classifier — SOLE decider
  custom_financial_calc.py       # Indicator computation; builds feature vector and delegates to the engine
  general.py                     # Decision extraction + action column (technical decides, LLM audit veto)
  llms.py                        # GPT auditor (audit_buy_signal) + legacy GPT/DeepSeek helpers
  risk_management.py             # Stop-loss, position sizing, correlation filter
  backtesting.py                 # Historical signal simulation
  historicals.py                 # Yahoo Finance + Alpha Vantage data fetching
  finnhub_client.py              # Finnhub market data
  google_handler.py              # Google Drive read/write
  email_handler.py               # Email notifications
  news_sentiment.py              # Finnhub news + earnings + GPT sentiment filter
test/                            # Tests, fully mocked
resources/
  technical_config.json          # Indicators, weights, regime rules, thresholds (the engine's config)
  ...                            # CSV data, symbol mappings
.github/workflows/               # CI (tests) + daily execution
```

## ⚠️ Disclaimer

This repository is for **educational and personal use only**. It is not financial advice. Trading involves risk of loss. Use responsibly and at your own risk.
