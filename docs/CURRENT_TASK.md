# Current Task

## Stage
**Build (Prompts 4–18) — IN PROGRESS.** Prompt 6 complete; starting Prompt 7.

The foundation stage (Prompts 1–3) is complete and committed on
`feature/close-assistant-build`.

## What is actively happening
Step 7 — Reconciliation Logic.

- Build a Pandas-based reconciliation module in `core/reconciliation/` that compares
  ``Transaction`` and ``BankTransaction`` records for a month.
- Match on vendor, amount within $0.01, and date within 1 day.
- Create ``Flag`` records with ``flag_type="reconciliation"`` for unmatched or
  mismatched pairs and one-sided entries.
- Wire it into a `run_reconciliation` management command that takes a month argument.
- Write tests first (TDD), implement, then commit.

## Status
- [x] Prompt 1 — scaffold.
- [x] Prompt 2 — models/migrations/admin.
- [x] Prompt 3 — QuickBooks OAuth + sync.
- [x] Prompt 4 — QuickBooks secrets & environment config.
- [x] Prompt 5 — Error handling & edge cases (QuickBooks sync).
- [x] Prompt 6 — Fake bank feed generator.
- [ ] Prompt 7 — Reconciliation logic.
- [ ] Prompts 8–18 — queued.

## Decision / blocker notes
- Live sandbox pull was **not** exercised in Prompt 3 (no credentials); mocked
  tests only.
- Docker test context from `AGENTS.md` applies once Docker is added in Prompt 15;
  Prompts 4–14 continue to use local Postgres.
- See `docs/TODO.md` for open follow-ups.

## Next step
Implement Prompt 7 test-first, keep tests green, commit, then move to Prompt 8.
