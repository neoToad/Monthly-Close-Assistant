# Changelog

All notable changes to the Monthly Close Assistant are recorded here, one entry per
commit, per the AGENTS.md workflow.

Archived changelogs live in `docs/changelogs/`.

## 2026-06-20

### Step 1 — `feat(models): add BankTransaction.source field and synthetic source tracking`
- Added `BankTransactionSource` choices (`synthetic`, `csv_import`, `bank_feed_api`, `manual`).
- Added `source` column to `BankTransaction` with `manual` default.
- Updated the squashed `core/migrations/0001_initial.py` directly so `makemigrations --check --dry-run` reports no changes.
- Updated `generate_bank_feed` in `core/engines/bank_feed.py` to set `source=synthetic` on every created row.
- Added model tests in `core/tests/test_models.py` and command tests in `core/tests/test_management.py` for source defaults and synthetic tracking.

### Step 2 — `feat(engines): add CSV import engine for BankTransaction rows`
- Added `core/engines/bank_feed_import.py` with `import_bank_feed_from_csv`.
- Supports required `date`/`amount` columns plus optional `vendor`, `category`, `gl_account`, `external_id`, and `description`.
- Validates `YYYY-MM-DD`, `MM/DD/YYYY`, and `DD-MM-YYYY` date formats; decimal amounts; and month containment.
- Enforces idempotency for `(company, month)` and supports `force=True` overwrite.
- Exported from `core/engines/__init__.py`.
- Added `core/tests/test_bank_feed_import.py` covering happy path, validation errors, out-of-month rows, and force behavior.

### Step 3 — `feat(management): add import_bank_feed command and dashboard view`
- Added `core/management/commands/import_bank_feed.py` for production CSV imports.
- Added `import_bank_feed_view` wired to `POST /dashboard/bank-feed/import/` with file size/type validation and UTF-8 decoding.
- Updated `core/templates/core/dashboard_content.html`:
  - Relabeled generator button to "Generate Synthetic Bank Feed" with testing-only subtitle.
  - Added multipart "Import Bank Feed CSV" form with subtitle.
- Clarified `generate_bank_feed` command help text as "(Testing/simulator only)".
- Added `ImportBankFeedCommandTests` in `core/tests/test_management.py` and `ImportBankFeedViewTests` in `core/tests/test_views.py`.
- Updated `_render_dashboard` to accept an optional HTTP status code.
