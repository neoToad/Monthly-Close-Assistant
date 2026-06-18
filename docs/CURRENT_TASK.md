# Current Task

## Stage
**Build (Prompts 4–18) — IN PROGRESS.** Prompt 8 complete; starting Prompt 9.

The foundation stage (Prompts 1–3) is complete and committed on
`feature/close-assistant-build`.

## What is actively happening
Step 9 — Idempotency for Reconciliation & Sync.

- Ensure re-running `run_reconciliation` does not duplicate `Flag` records.
- Keep `sync_quickbooks` idempotent via `qb_transaction_id`.
- Make `generate_bank_feed` prompt or require `--force` if bank data already exists
  for the month.
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
- [ ] Prompt 9 — Idempotency for reconciliation & sync.
- [ ] Prompts 10–18 — queued.

## Decision / blocker notes
- Live sandbox pull was **not** exercised in Prompt 3 (no credentials); mocked
  tests only.
- Docker test context from `AGENTS.md` applies once Docker is added in Prompt 15;
  Prompts 4–14 continue to use local Postgres.
- See `docs/TODO.md` for open follow-ups.

## Next step
Implement Prompt 9 test-first, keep tests green, commit, then move to Prompt 10.
