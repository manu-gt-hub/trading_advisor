# POLICY: Commits and pushes (HARD RULE)

## Before ANY `git commit` — always, with ONE exception

1. Show the user a summary of pending changes: files, what changed, why,
   test/backtest status.
2. Propose the commit message.
3. Wait for explicit confirmation ("commit it", "yes", "hazlo"...).

**Exception — auto-commit authorization:** if the user explicitly says, when
launching the task/order, that the agent may commit automatically (e.g.
"hazlo y commitea", "implement and commit", "commitea directamente cuando
termines"), the summary-before-commit step can be skipped and the agent may
commit as part of completing the task. The authorization must be explicit and
for that task — it does not carry over to future tasks. Even under auto-commit,
the agent should still show what it committed afterwards.

Never batch a commit into a larger "approved" action without listing it as
pending (unless the user used the auto-commit phrasing above).

## `git push` requires its own separate approval

A commit approval does not imply push approval. Ask again.

## Never commit

- Secrets, API keys, credentials, `.env` files, tokens.
- Files under version control that contain real transaction data unless asked.
- Scratch/temp analysis scripts (e.g. `_*.py` helpers) — delete them first.

## Commit message style

Match `git log` history: `type: short summary` (feat/fix/docs/refactor/test),
plus a body explaining **why**, not what. Example:

```
feat: raise min_momentum_for_buy to 0.35

Backtest neutral but filters weak-momentum entries in production.
Baseline unchanged; see BACKTEST_LOG.md 2026-09-23 entry.
```
