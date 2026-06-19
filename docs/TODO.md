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
