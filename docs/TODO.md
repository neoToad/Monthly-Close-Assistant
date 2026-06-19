# TODO

## Multi-company QuickBooks support

- ✅ Create `QuickBooksCompany` model with `realm_id` as primary key.
- ✅ Add `company` foreign keys to `Transaction`, `BankTransaction`, `Flag`,
  `CloseSummary`, `QBAccount`, `BankStatementBalance`, and `QBToken`.
- ✅ Backfill existing rows via migration and replace `(realm_id, ...)` unique
  constraints with `(company, ...)`.
- ✅ Add `QuickBooksCompanyManager.for_realm(realm_id)` helper and update all
  creation paths.
- ✅ Update tests and docs.

## Bank balance reconciliation

- ✅ Add `BankStatementBalance` model and `BALANCE_RECONCILIATION` flag type.
- ✅ Add `set_bank_balance` manual-entry command.
- ✅ Add QB `seed_bank_balances` sandbox auto-seeder.
- ✅ Integrate balance check into `run_reconciliation` and add tests.
- ✅ Expose bank balances on the dashboard with inline set-balance form.
- ✅ Update README and CHANGELOG.

## AI-assisted account reconciliation

- ✅ Add `AccountReconciliationState` model and `ReconciliationStatus` choices.
- ✅ Add deterministic account-level suggestion engine with optional LLM path.
- ✅ Add QuickBooks write wrappers for JournalEntry / Purchase / Deposit.
- ✅ Add reconcile-account modal, preview, confirmation, and dashboard integration.
- ✅ Add `suggest_account_fixes` and `apply_account_fix` management commands.
- ✅ Add model, agent, write, view, and command tests.
- ✅ Update README, CHANGELOG, and TODO.

## Synthetic bank feed

- ✅ Add `generate_bank_feed` management command for synthetic bank transactions.
- ✅ Expose Generate Bank Feed action on the dashboard with force/cash-only support.
- ✅ Add view tests for dashboard generation.

## Refactor plan (`docs/plans/refactor_plan.md`)

### Step 1 — Audit

- ✅ Document module/package structure and conceptual-architecture drift.
- ✅ Catalog business logic living in `core/views.py`.
- ✅ List duplicated logic across engines (`_month_bounds`, `_prior_month`,
  `CASH_LIKE_ACCOUNT_TYPES`, posted-GL sums, LLM plumbing, realm resolution).
- ✅ Document inconsistent naming and thin docstrings.
- ✅ Record type-hint and error-handling gaps.
- ✅ Summarize test-coverage gaps, dead code, and best-practice opportunities.
- ✅ Produce sequenced execution plan and open questions.

### Step 2 — Refactor execution

- ⬜ Dead code cleanup (2.7.A–F).
- ⬜ Centralize dates and constants (2.2.C).
- ⬜ Type hints and docstrings pass (2.4).
- ⬜ Extract `compute_posted_total` and grouped queries (2.1.B, 2.8.A).
- ⬜ Extract service layer for apply flow (2.1.A).
- ⬜ Move QB write helpers to `core/services/qb_writes.py` (2.1.C).
- ⬜ Centralize retry/backoff (2.5.A).
- ⬜ Add missing idempotency tests (2.6).
- ⬜ Package reorganization (2.2.A full target).
- ⬜ Migration squash (2.8.E).
