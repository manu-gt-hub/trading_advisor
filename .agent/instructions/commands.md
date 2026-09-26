# Commands

```bash
# Install
pip install -r requirements.txt

# Full test suite (~117 tests, fully mocked, ~12s)
python -m pytest test/ -q

# Single test file / test
python -m pytest test/test_backtesting.py -q
python -m pytest test/test_backtesting.py::test_name -q

# Engine validation backtest (offline; only yfinance valuation fetch needs net,
# SSL warnings are expected in some environments and are non-fatal)
python run_backtest_all.py

# Production run (needs env vars — see env_vars.md)
python main.py
python main.py --test   # debug output
```

## Notes

- The repo is Windows-hosted; the agent shell may be bash (Git Bash). Prefer
  forward-compatible paths and `python` over `py`.
- Tests are fully mocked — no API keys needed for pytest.
- `run_backtest_all.py` uses `resources/historicals/*.csv`; `step_days=5`,
  `min_history=250`, target 10%, max hold 30 days by default.
