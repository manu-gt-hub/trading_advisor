# POLICY: Secrets and credentials (HARD RULE)

- **Never** read, print, log, or commit secrets: `FINNHUB_API_KEY`,
  `OPENAI_API_KEY`, `ALPHA_API_KEY`, `GDRIVE_CREDENTIALS_JSON`, `.env` contents.
- If a test or config needs a key, reference the env var name — never a value.
- If you find a secret already committed in history, STOP and report to the user
  (rotation + history scrub is a destructive op requiring explicit approval).
- `.env` must stay in `.gitignore`. If it isn't listed, add it — that's a
  security fix you may make without asking, but report it.
