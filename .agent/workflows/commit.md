# WORKFLOW: Committing

## Steps

1. `git status` + `git diff` — list exactly what changed.
2. Verify: `python -m pytest test/ -q` green.
3. If engine change: verify `docs/BACKTEST_LOG.md` was updated (approval already
   obtained via engine_change workflow).
4. Check for stray files: temp scripts (`_*.py`), `.env`, credentials → remove
   or refuse.
5. Present to the user:
   - file list + what changed + why
   - test/backtest status
   - proposed commit message (`type: summary` + why-body)
6. Wait for explicit approval → `git commit`.
   **Exception**: if the user explicitly authorized auto-commit when launching
   the task ("hazlo y commitea", "commit automatically when done"), skip steps
   5–6 and commit directly — then report what was committed afterwards.
7. Ask separately about `git push` — never assume it.
