# Current Task

## Stage
**Build (Prompts 4–18) — IN PROGRESS.** Prompt 12 complete; starting Prompt 13.

The foundation stage (Prompts 1–3) is complete and committed on
`feature/close-assistant-build`.

## What is actively happening
Step 13 — HTMX Review Dashboard.

- Build `/dashboard/` with a month selector (`hx-get`).
- Show a table of open flags with Approve/Reject buttons (`hx-post` partial row swap).
- Show a CloseSummary draft section with a Mark Reviewed action and reviewer notes
  field.
- Write tests first (TDD), implement, then commit.

## Status
- [x] Prompt 1 — scaffold.
- [x] Prompt 2 — models/migrations/admin.
- [x] Prompt 3 — QuickBooks OAuth + sync.
- [x] Prompt 4 — QuickBooks secrets & environment config.
- [x] Prompt 5 — Error handling & edge cases (QuickBooks sync).
- [x] Prompt 6 — Fake bank feed generator.
- [x] Prompt 7 — Reconciliation logic.
- [x] Prompt 8 — Anomaly detection.
- [x] Prompt 9 — Idempotency for reconciliation & sync.
- [x] Prompt 10 — Agent layer / close-summary generation.
- [x] Prompt 11 — Demo data seeding.
- [x] Prompt 12 — Celery scheduled sync.
- [ ] Prompt 13 — HTMX review dashboard.
- [ ] Prompts 14–18 — queued.

## Decision / blocker notes
- Live sandbox pull was **not** exercised in Prompt 3 (no credentials); mocked
  tests only.
- Live Anthropic summary generation was **not** exercised in Prompt 10; tests use
  the deterministic fallback and a fake LLM client.
- Docker test context from `AGENTS.md` applies once Docker is added in Prompt 15;
  Prompts 4–14 continue to use local Postgres.
- See `docs/TODO.md` for open follow-ups.

## Next step
Implement Prompt 13 test-first, keep tests green, commit, then move to Prompt 14.
