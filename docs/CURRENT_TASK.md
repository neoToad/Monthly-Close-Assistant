# Current Task

## Stage
**Build (Prompts 4–18) — IN PROGRESS.** Prompt 7 complete; starting Prompt 8.

The foundation stage (Prompts 1–3) is complete and committed on
`feature/close-assistant-build`.

## What is actively happening
Step 8 — Anomaly Detection.

- Add rule-based anomaly checks on a month's ``Transaction`` data:
  * vendor amount > 2σ from historical average
  * duplicate transactions within a 7-day window
  * new vendors with no prior history
  * categories with > 200% month-over-month change
- Create ``Flag`` records with ``flag_type="anomaly"`` and clear reasons.
- Integrate anomaly detection into `run_reconciliation` so it runs both
  reconciliation and anomaly checks together.
- Write tests first (TDD), implement, then commit.

## Status
- [x] Prompt 1 — scaffold.
- [x] Prompt 2 — models/migrations/admin.
- [x] Prompt 3 — QuickBooks OAuth + sync.
- [x] Prompt 4 — QuickBooks secrets & environment config.
- [x] Prompt 5 — Error handling & edge cases (QuickBooks sync).
- [x] Prompt 6 — Fake bank feed generator.
- [x] Prompt 7 — Reconciliation logic.
- [ ] Prompt 8 — Anomaly detection.
- [ ] Prompts 9–18 — queued.

## Decision / blocker notes
- Live sandbox pull was **not** exercised in Prompt 3 (no credentials); mocked
  tests only.
- Docker test context from `AGENTS.md` applies once Docker is added in Prompt 15;
  Prompts 4–14 continue to use local Postgres.
- See `docs/TODO.md` for open follow-ups.

## Next step
Implement Prompt 8 test-first, keep tests green, commit, then move to Prompt 9.
