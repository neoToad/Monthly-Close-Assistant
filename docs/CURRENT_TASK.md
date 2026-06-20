# Current Task

ConnectWise Step 2 — QBO customer/invoice sync

Actively working on:
- Added `sync_customers` and `sync_invoices` helpers to `core/quickbooks/client.py`.
- Wired the helpers into the `sync_quickbooks` management command.
- Added `--skip-customers` and `--skip-invoices` flags.
- Added `core/tests/test_qbo_invoice_sync.py` with mocked SDK tests.
- Updated existing sync command tests to patch the new helpers.

Blockers or decisions:
- None.

Next step:
- After commit and push, move to Step 3 (synthetic ConnectWise feed).
