# WORKFLOW: Adding a tunable parameter

1. Add the key to `resources/technical_config.json` with a safe default —
   deployments without the key must behave as before.
2. Read it in code with `config.get("new_key", <same default>)`.
3. If it affects the decision path → this IS an engine change →
   follow `engine_change.md` (baseline backtest before touching anything).
4. Document it in `resources/doc/06_configuration.md`.
5. If it's deployment-time (not analysis-time), prefer an env var and document
   in `.agent/instructions/env_vars.md` + `README.md` env table.
