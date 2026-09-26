# Environment variables

## Required for production (`main.py`)

| Variable | Purpose |
|---|---|
| `SYMBOLS_INTEREST_LIST` | Python-list literal, e.g. `"['NVDA','MSFT']"` — **US exchanges only** (Finnhub free) |
| `FINNHUB_API_KEY` | Quotes + news |
| `OPENAI_API_KEY` | GPT audit + news sentiment |
| `GPT_MODEL_NAME` | default `gpt-4o` |
| `GDRIVE_CREDENTIALS_JSON` | Service-account JSON |
| `GDRIVE_FILE_ID` | Transactions sheet |
| `BUY_RECOMMENDATIONS_ID` | Buy recommendations sheet |
| `ANALYSIS_FILE_ID` | Analysis sheet |
| `REVENUE_PERCENTAGE` | Take-profit % (e.g. `10`) |

## Tunables

| Variable | Default | Purpose |
|---|---|---|
| `MIN_BUY_CONFIDENCE` | 0.6 prod (0.45 in backtests) | Min confidence for BUY |
| `MIN_RISK_REWARD_RATIO` | 1.2 | Min R:R (ATR stop vs target) |
| `LLM_AUDIT_ENABLED` | true | GPT audit of BUY signals (recommend `false`) |
| `NEWS_SENT_ANALYSIS` | false | News/earnings filter |
| `FORCE_OPINION` | DEFAULT | DEFAULT / CUSTOM / LLM1 / LLM2 |
| `TRANSACTIONS_MAX_RECORDS` | 100 | Sheet cap |
| `LOG_LEVEL` | INFO | Logging |

## Data feeds

| Variable | Purpose |
|---|---|
| `ALPHA_API_KEY`, `ALPHA_VANTAGE_URL` | Historical data refresh |
| `DISABLE_SSL_VERIFY` | Set only if env has broken cert chain |
| `DEEPKSEEK_API_KEY` | Legacy/experimental LLM |

## Environment notes

- `GITHUB_ACTIONS` is auto-set in CI — code branches on it for `.env` loading.
- Finnhub free tier: **US exchanges only**. `.L`, `.DE`, `.PA`, etc. → 403/zeros.
  The system skips invalid quotes safely but the symbol gets no analysis.
