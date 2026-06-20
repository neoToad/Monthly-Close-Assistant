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

### Step 4 — `feat(engines): add independent bank-feed scenarios to simulator`
- Added `core/fixtures/` package and `core/fixtures/bank_feed_scenarios/independent_default.json` with realistic bank descriptions.
- Extended `generate_bank_feed` in `core/engines/bank_feed.py` to support `scenario` (`derived`/`independent`) and `scenario_file`.
- Refactored discrepancy logic into `_apply_discrepancies` helper shared by both scenarios.
- Independent scenario ignores GL transactions, randomizes dates within the month, applies discrepancies, and marks rows `source=synthetic`.
- Updated `core/management/commands/generate_bank_feed.py` with `--scenario` and `--scenario-file` arguments and scenario-labeled output.
- Added command tests for derived, independent, and custom scenario fixtures.
