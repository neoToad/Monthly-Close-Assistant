# Plan: Remove Dummy Data and Use Real QuickBooks Data

## Goal
Stop using synthetic demo transactions as the primary data path. Make QuickBooks Online the only source of GL `Transaction` records, keep the fake bank feed available as an opt-in testing tool, and provide dashboard actions for the real-data workflow.

## Current State
- `seed_demo_data` generates fake `Transaction` rows with `DEMO-*` IDs.
- `generate_bank_feed` derives deliberately imperfect `BankTransaction` rows from whatever `Transaction` rows exist.
- `sync_quickbooks` already pulls real Purchase / Deposit / JournalEntry records from QuickBooks and normalizes them into `Transaction` rows (idempotent on `qb_transaction_id`).
- The dashboard shows flags + close summaries for a month, but has no UI action to sync, reconcile, or draft summaries.

## Chosen Approach — Option B
- **Remove** the fake GL transaction generator (`seed_demo_data`).
- **Keep** the fake bank feed generator (`generate_bank_feed`) but relabel/document it as a reconciliation-testing helper, not part of the normal production workflow.
- **Add** dashboard actions so a user can connect QuickBooks, sync, reconcile, and draft a close summary without touching the command line.

## Implementation Steps

### Step 1 — Remove demo transaction generator
- Delete `core/demo_seed.py`.
- Delete `core/management/commands/seed_demo_data.py`.
- Remove `faker` from `requirements.txt` (only used by demo seeding).
- Update `README.md` and `docs/Monthly_Close_Assistant_Project.md` to remove demo-data instructions.

### Step 2 — Relabel fake bank feed as testing-only
- Update `core/bank_feed.py` docstring to emphasize it is for testing reconciliation logic, not production data.
- Update `core/management/commands/generate_bank_feed.py` help text similarly.
- Keep the command and tests intact; it remains usable via `python manage.py generate_bank_feed YYYY-MM --force` for manual testing.

### Step 3 — Add dashboard actions for real data workflow
Add HTMX-powered buttons to `core/templates/core/dashboard_content.html` and new views in `core/views.py`:
- **Sync QuickBooks** — POST to `qb_sync_now` view that calls the existing `sync_quickbooks` logic, returns a status message, and refreshes dashboard content.
- **Run reconciliation** — POST to `reconcile_month` view that calls `run_reconciliation(month)`.
- **Draft close summary** — POST to `draft_summary` view that calls `draft_close_summary(month)`.
- All views require `@login_required` and `@require_POST`.
- Wire new paths in `core/urls.py`.

### Step 4 — Update navigation and empty states
- `core/templates/core/home.html`: update copy to emphasize QuickBooks connection.
- `core/templates/core/dashboard_content.html`: show a helpful empty state when a month has no transactions, with a "Sync QuickBooks now" prompt.
- `core/templates/base.html`: keep "Connect QuickBooks" / "Dashboard" / "Admin" links for authenticated users; no changes needed.

### Step 5 — Update tests
- Remove `SeedDemoDataCommandTests` from `core/tests/test_management.py`.
- Remove / update any other tests that depend on `seed_demo_data`.
- Add tests for the new dashboard views: sync trigger, reconcile trigger, draft summary trigger.
- Keep existing tests for `sync_quickbooks`, `generate_bank_feed`, reconciliation, anomaly detection, and close summary.

### Step 6 — Documentation + changelog
- Update `docs/TODO.md` with the new step checklist.
- Append an entry to `docs/CHANGELOG.md` after the implementation commit.
- Update `docs/CURRENT_TASK.md` to reflect live state throughout implementation.
- Update `README.md` management command table: remove `seed_demo_data`, relabel `generate_bank_feed` as testing-only.

## Files Expected to Change
- `core/demo_seed.py` — delete
- `core/management/commands/seed_demo_data.py` — delete
- `requirements.txt` — remove `faker`
- `core/management/commands/generate_bank_feed.py` — update help text
- `core/bank_feed.py` — update docstring
- `core/views.py` — add `qb_sync_now`, `reconcile_month`, `draft_summary`
- `core/urls.py` — add new paths
- `core/templates/core/dashboard_content.html` — add action buttons + empty state
- `core/templates/core/home.html` — update copy
- `core/tests/test_management.py` — remove demo tests
- `core/tests/test_views.py` — add dashboard action tests
- `README.md` — remove demo commands
- `docs/Monthly_Close_Assistant_Project.md` — remove demo references
- `docs/TODO.md`, `docs/CHANGELOG.md`, `docs/CURRENT_TASK.md` — tracking updates

## Open Questions / Decisions
- None — Option B selected by user.