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
| `MIN_BUY_CONFIDENCE` | engine: 0.5 (`buy_threshold_default`); post-audit filter: 0.6 | Min confidence for BUY — set it explicitly so both agree; the backtest reads it too |
| `MIN_RISK_REWARD_RATIO` | 1.2 | Min R:R (ATR stop vs target) |
| `LLM_AUDIT_ENABLED` | true | GPT audit of BUY signals (recommend `false`) |
| `NEWS_SENT_ANALYSIS` | false | News/earnings filter |
| `FORCE_OPINION` | DEFAULT | DEFAULT / CUSTOM (legacy LLM1/LLM2 fall back to DEFAULT) |
| `TRANSACTIONS_MAX_RECORDS` | 100 | Sheet cap |
| `LOG_LEVEL` | INFO | Logging |

## Data feeds

| Variable | Purpose |
|---|---|
| `ALPHA_API_KEY`, `ALPHA_VANTAGE_URL` | Historical data refresh |
| `DISABLE_SSL_VERIFY` | Set only if env has broken cert chain |

## Environment notes

- `GITHUB_ACTIONS` is auto-set in CI — code branches on it for `.env` loading.
- API keys are masked in logs (`general.SecretRedactingFilter`); Finnhub is
  authenticated via the `X-Finnhub-Token` header, never the URL.
- Finnhub free tier: **US exchanges only**. `.L`, `.DE`, `.PA`, etc. → 403/zeros.
  The system skips invalid quotes safely but the symbol gets no analysis.
