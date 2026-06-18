# Current Task

## Stage
**Build (Prompts 4–18) — IN PROGRESS.** Prompt 10 complete; starting Prompt 11.

The foundation stage (Prompts 1–3) is complete and committed on
`feature/close-assistant-build`.

## What is actively happening
Step 11 — Demo Data Seeding.

- Create a single `seed_demo_data` management command.
- The command should create demo ``Transaction`` records with Faker, run
  `generate_bank_feed`, run reconciliation + anomaly detection, and run the agent
  summary generator.
- Ensure it is safe to run repeatedly without duplicates (idempotent).
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
- [ ] Prompt 11 — Demo data seeding.
- [ ] Prompts 12–18 — queued.

## Decision / blocker notes
- Live sandbox pull was **not** exercised in Prompt 3 (no credentials); mocked
  tests only.
- Live Anthropic summary generation was **not** exercised in Prompt 10; tests use
  the deterministic fallback and a fake LLM client.
- Docker test context from `AGENTS.md` applies once Docker is added in Prompt 15;
  Prompts 4–14 continue to use local Postgres.
- See `docs/TODO.md` for open follow-ups.

## Next step
Implement Prompt 11 test-first, keep tests green, commit, then move to Prompt 12.
