# Current Task

## Stage
Foundation (Prompts 1–3) — in progress.

## Current step
**Step 2 — Postgres Schema** (active, TDD). Step 1 is complete and committed; see
CHANGELOG.md.

## What I am actively working on
Adding the four `core` models per the spec, test-first:
- **Transaction** — QuickBooks-sourced: date, vendor, amount, category, gl_account,
  qb_transaction_id, source_type.
- **BankTransaction** — same shape as Transaction, plus a nullable
  `matched_transaction_id` FK → Transaction (the bank-feed side).
- **Flag** — flag_type, related transaction or bank_transaction, reason, severity,
  status [open/approved/rejected], created_at.
- **CloseSummary** — month, summary_text, status [draft/reviewed], reviewer_notes,
  created_at.

Then write + apply migrations and register all four models in Django admin.

## TDD status
- [ ] Write `core/tests/test_models.py` (field shapes, choices, nullable FK, `__str__`,
      admin registration via `admin.site._registry`) and confirm failures.
- [ ] Build models, `makemigrations`, `migrate`, register in admin.
- [ ] Tests green (`python manage.py test`).

## Decisions / blockers
- Same environment as Step 1: PyCharm venv `../.venvs/MonthlyCloseAssistant`,
  Docker Postgres `close_pg` on host port 5434 (db `close_assistant`, user `close_app`).
- Exact field types/choices will be pinned in the tests first, then implemented.

## Next step
Finish Step 2 (tests green + migrate) → commit & push → Step 3 (QuickBooks OAuth +
`sync_quickbooks`).