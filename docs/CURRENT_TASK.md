# Current Task

## Stage
**Build (Prompts 4–18) — IN PROGRESS.** Prompt 9 complete; starting Prompt 10.

The foundation stage (Prompts 1–3) is complete and committed on
`feature/close-assistant-build`.

## What is actively happening
Step 10 — Agent Layer.

- Install and configure an agent framework (CrewAI, or LangGraph +
  LangChain-Anthropic).
- Build a step that reads open `Flag` records plus monthly category totals /
  prior-month comparison, then drafts a plain-language close summary.
- Save the result as a `CloseSummary` with `status="draft"`.
- Wire it into a `generate_close_summary` management command.
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
- [ ] Prompt 10 — Agent layer / close-summary generation.
- [ ] Prompts 11–18 — queued.

## Decision / blocker notes
- Live sandbox pull was **not** exercised in Prompt 3 (no credentials); mocked
  tests only.
- Docker test context from `AGENTS.md` applies once Docker is added in Prompt 15;
  Prompts 4–14 continue to use local Postgres.
- See `docs/TODO.md` for open follow-ups.

## Next step
Implement Prompt 10 test-first, keep tests green, commit, then move to Prompt 11.
