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

## Design System (D1–D7)

- [x] D1 — Design Tokens & Base Styles
- [x] D2 — Page Shell & Header
- [x] D3 — Flagged Items Table Redesign
- [x] D4 — Draft Summary Section
- [x] D5 — Empty & Loading States
- [x] D6 — Responsive & Accessibility Pass
- [x] D7 — Self-Critique Pass
