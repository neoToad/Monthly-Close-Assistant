# TODO

## Multi-company QuickBooks support

- [x] Add `realm_id` to `Transaction`, `BankTransaction`, `Flag`, and `CloseSummary`.
- [x] Introduce `QuickBooksCompany` model for connected realms.
- [x] Update unique constraints to `(realm_id, qb_transaction_id)` and `(realm_id, month)`.
- [x] Backfill legacy rows in migration 0003 from the most recent `QBToken`.
- [x] Scope QuickBooks sync by realm and sync all connected companies by default.
- [x] Scope reconciliation, anomaly detection, bank feed, and close summary by `realm_id`.
- [x] Add `--realm-id` to management commands.
- [x] Add company selector to the dashboard and pass `realm_id` through actions.
- [x] Add behavior tests verifying cross-realm isolation.
- [x] Update README / DEPLOY / project docs.
- [x] Run full test suite and commit.

## QuickBooks company name fetch

- [x] Add `CompanyInfo` fetch helper (`fetch_company_name`) in `core/quickbooks/client.py`.
- [x] Update `store_tokens` to accept and preserve `company_name`.
- [x] Fetch and store name during OAuth callback.
- [x] Refresh name during `sync_quickbooks` command.
- [x] Remove spurious token methods from `QuickBooksCompany`.
- [x] Write TDD tests for name fetch, callback, sync command, and model cleanup.
- [x] Update docs (`PLAN.md`, `CHANGELOG.md`, `README.md`, `CURRENT_TASK.md`).

## Add QuickBooks data sources

- [x] Add `Bill`, `BillPayment`, `VendorCredit` to `SourceType` and `QBAccount` model
- [x] Extend `SYNC_OBJECTS` and `normalize_record` for the three AP types
- [x] Add `sync_accounts` helper and wire into `sync_quickbooks`
- [x] Print per-type counts for new transaction sources
- [x] Add normalization, account sync, and sync-command tests
- [x] Add realm-isolation tests for `QBAccount`
- [x] Scope bank feed to cash-like transaction types with `--cash-only`
- [ ] Add `fetch_general_ledger_summary` and include in close-summary inputs
- [ ] Update README and project docs
- [ ] Run full test suite and commit each step

## Design System (D1–D7)

- [x] D1 — Design Tokens & Base Styles
- [x] D2 — Page Shell & Header
- [x] D3 — Flagged Items Table Redesign
- [x] D4 — Draft Summary Section
- [x] D5 — Empty & Loading States
- [x] D6 — Responsive & Accessibility Pass
- [x] D7 — Self-Critique Pass
