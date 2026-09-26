# .agent/ — Agent harness modules

Modular instructions for AI coding agents. `../AGENTS.md` is the entry point and
remains canonical; this directory holds the detailed modules it references.

```
.agent/
├── instructions/   # Static context: architecture, engine, commands, env vars
├── workflows/      # Step-by-step procedures (SOPs) for recurring task types
└── policies/       # Hard rules — violations mean the task is not done
```

## Reading order for a new agent

1. `../AGENTS.md` — overview + all rules (read this first, always)
2. `instructions/architecture.md` — if you need the module map
3. `instructions/engine.md` — if touching the decision path
4. `workflows/engine_change.md` — if modifying engine/config
5. `workflows/commit.md` — before any commit
6. `policies/*.md` — the hard rules, consult as needed

See `../evals/` for the evaluation harness used to grade agent behavior.
