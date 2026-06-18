# Current Task

## Stage
**Build (Prompts 4–18) — IN PROGRESS.** Prompt 4 complete; starting Prompt 5.

The foundation stage (Prompts 1–3) is complete and committed on
`feature/close-assistant-build`.

## What is actively happening
Step 5 — Error Handling & Edge Cases (QuickBooks Sync).

- Catch mid-sync access-token expiry, refresh the token once, and retry the request.
- Add exponential backoff for QuickBooks API rate limiting / timeouts (max 3 attempts).
- Ensure all failures produce clear log output (no silent crashes).
- Persist refreshed tokens back to ``QBToken`` after a refresh.

## Status
- [x] Prompt 1 — scaffold.
- [x] Prompt 2 — models/migrations/admin.
- [x] Prompt 3 — QuickBooks OAuth + sync.
- [x] Prompt 4 — QuickBooks secrets & environment config.
- [ ] Prompt 5 — Error handling & edge cases (QuickBooks sync).
- [ ] Prompts 6–18 — queued.

## Decision / blocker notes
- Live sandbox pull was **not** exercised in Prompt 3 (no credentials); mocked
  tests only.
- Docker test context from `AGENTS.md` applies once Docker is added in Prompt 15;
  Prompts 4–14 continue to use local Postgres.
- See `docs/TODO.md` for open follow-ups.

## Next step
Implement Prompt 5 test-first, keep tests green, commit, then move to Prompt 6.
