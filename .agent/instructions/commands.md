# Commands

```bash
# Install (runtime + pytest)
pip install -r requirements-dev.txt

# Full test suite (fully mocked/offline; Drive integration tests skip without credentials)
python -m pytest test/ -q

# Single test file / test
python -m pytest test/test_backtesting.py -q
python -m pytest test/test_backtesting.py::test_name -q

# Engine validation backtest (fully offline, replays the production pipeline)
python run_backtest_all.py
# Experiments only: --min-conf, --min-rr, --target, --step-days, --max-hold, --no-weekly
python run_backtest_all.py --max-hold 30

# Production run (needs env vars — see env_vars.md)
python main.py
python main.py --test   # debug output
```

## Notes

- The repo is Windows-hosted; the agent shell may be bash (Git Bash). Prefer
  forward-compatible paths and `python` over `py`.
- Tests are fully mocked — no API keys needed for pytest.
- `run_backtest_all.py` uses `resources/historicals/*.csv`. Parameters come from
  the `backtest` section of `technical_config.json`, overridden by the same env
  vars production reads (`REVENUE_PERCENTAGE`, `MIN_BUY_CONFIDENCE`,
  `MIN_RISK_REWARD_RATIO`); the resolved values are printed on the first line.
- Not replayable offline: LLM audit, news/earnings filter, correlation filter,
  valuation adjustment and real S&P500 context (mocked NEUTRAL).
