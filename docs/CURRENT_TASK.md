# Current Task

## Stage
**Build (Prompts 4–18) — IN PROGRESS.** Prompt 5 complete; starting Prompt 6.

The foundation stage (Prompts 1–3) is complete and committed on
`feature/close-assistant-build`.

## What is actively happening
Step 6 — Fake Bank Feed Generator.

- Create a `generate_bank_feed` management command that reads all `Transaction`
  records for a given month and generates `BankTransaction` records.
- Introduce configurable discrepancies: drop_rate, dup_rate, amount_shift_rate,
  date_shift_rate, extra_rate.
- Use Pandas for the manipulation and print a summary of discrepancies introduced.
- Write tests first (TDD), implement, then commit.

## Status
- [x] Prompt 1 — scaffold.
- [x] Prompt 2 — models/migrations/admin.
- [x] Prompt 3 — QuickBooks OAuth + sync.
- [x] Prompt 4 — QuickBooks secrets & environment config.
- [x] Prompt 5 — Error handling & edge cases (QuickBooks sync).
- [ ] Prompt 6 — Fake bank feed generator.
- [ ] Prompts 7–18 — queued.

## Decision / blocker notes
- Live sandbox pull was **not** exercised in Prompt 3 (no credentials); mocked
  tests only.
- Docker test context from `AGENTS.md` applies once Docker is added in Prompt 15;
  Prompts 4–14 continue to use local Postgres.
- See `docs/TODO.md` for open follow-ups.

## Next step
Implement Prompt 6 test-first, keep tests green, commit, then move to Prompt 7.
