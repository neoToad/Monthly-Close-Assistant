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
