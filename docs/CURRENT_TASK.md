# CURRENT_TASK

## Stage

Multi-company QuickBooks support is implemented and tested.

## Current task

**Done:**

- Schema: `realm_id` added to `Transaction`, `BankTransaction`, `Flag`, and `CloseSummary`.
- `QuickBooksCompany` model tracks each connected realm.
- Unique constraints changed to `(realm_id, qb_transaction_id)` and `(realm_id, month)`.
- `run_reconciliation(month, realm_id=None)` filters both GL and bank sides and scopes flags by realm.
- `run_anomaly_detection(month, realm_id=None)` filters transactions and scopes anomaly flags by realm.
- `draft_close_summary(month, realm_id=None)` filters inputs and saves per `(realm_id, month)`.
- `generate_bank_feed(month, ..., realm_id=None)` filters source transactions and scopes generated bank rows by realm.
- `--realm-id` added to `sync_quickbooks`, `run_reconciliation`, `generate_close_summary`, and `generate_bank_feed` commands.
- Dashboard includes a company selector and passes `realm_id` through sync/reconcile/summary actions.
- Behavior tests in `core/tests/test_multi_company.py` verify isolation across realms.
- Full test suite: **176 tests pass**.

## Branch

`feature/close-assistant-build`

## Next step

Update project documentation (`README.md`, `docs/DEPLOY.md`, `docs/TODO.md`, `docs/CHANGELOG.md`) and commit.
