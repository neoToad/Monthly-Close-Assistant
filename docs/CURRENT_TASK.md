# CURRENT_TASK

## Stage

Company-FK refactor is complete. All realm-scoped models are now attached to
`QuickBooksCompany` via foreign keys, with `realm_id` retained as a denormalized
indexed filter.

## Completed

- Added `company` foreign keys to `Transaction`, `BankTransaction`, `Flag`,
  `CloseSummary`, `QBAccount`, `BankStatementBalance`, and `QBToken`.
- Generated and hand-edited migration `0006` to add nullable FKs, backfill via
  `QuickBooksCompany.objects.for_realm(realm_id)`, then make the FKs non-nullable
  and replace unique constraints.
- Updated all creation paths (sync, tokens, bank feed, reconciliation, anomaly,
  summary, dashboard, management commands) to resolve and write `company`.
- Updated every test helper and fixture to pass `company`; full `core.tests`
  suite passes **232 tests**.
- Updated `README.md`, `docs/CHANGELOG.md`, and `docs/TODO.md`.

## Branch

`feature/close-assistant-build`

## Next step

Commit the company-FK refactor. After that, resume bank-balance reconciliation
polish or the next planned feature.
