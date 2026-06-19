# CURRENT_TASK

## Stage

Implementing `docs/plans/add_quickbooks_data_sources_plan.md`.

## Current step

**Step 4 — Scope bank feed to cash-like transaction types**
- Add `cash_only: bool = False` parameter to `core/bank_feed.py::generate_bank_feed()`.
- When `cash_only=True`, restrict source `Transaction` rows to cash movement types:
  `Purchase`, `Deposit`, `BillPayment`, and `JournalEntry` (only when `gl_account`
  maps to a cash-like `QBAccount`; include by default if `QBAccount` data is missing).
- Add `--cash-only` flag to `core/management/commands/generate_bank_feed.py`.
- Write failing tests first, then implement.

## Branch

`feature/close-assistant-build`

## Next step

Commit `feat(reconcile): scope bank feed to cash-like transaction types`, then begin Step 5.
