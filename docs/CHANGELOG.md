# Changelog

All notable changes to the Monthly Close Assistant are recorded here, one entry per
commit, per the AGENTS.md workflow.

Archived changelogs live in `docs/changelogs/`.

## 2026-06-20

### Step 7 — `feat(demo): add seed_demo_msp_data command with realistic MSP fixture`
- Added `core/fixtures/msp_demo_data.py` with chart of accounts, customers, vendors,
  deposits, bills, purchases, journal entries, bill payments, and vendor credits for
  the fictional **Next Level Networks Demo** MSP.
- Added `core/management/commands/seed_demo_msp_data.py`:
  - Accepts `month` in `YYYY-MM`, optional `--realm-id` (default `demo-msp`),
    `--force`, `--include-bank-feed`, and `--seed`.
  - Creates the `QuickBooksCompany` and 12 `QBAccount` rows idempotently.
  - Seeds 20 signed `Transaction` rows so the balance-reconciliation check raises a
    flag against the seeded `$42,315.50` bank statement balance.
  - Supports date jitter via `--seed` while keeping amounts deterministic for stable
    assertions.
  - With `--include-bank-feed`, calls `generate_bank_feed` so `run_reconciliation`
    immediately produces reconciliation flags.
- Added `core/tests/test_seed_demo_msp_data.py` with 14 tests covering idempotency,
  force re-seed, transaction counts, bank statement balance, bank-feed integration,
  balance-reconciliation flags, and new-vendor anomaly flags.
- Updated `docs/TODO.md`, `docs/CURRENT_TASK.md`, and this changelog.
- Verification: `makemigrations --check --dry-run` reports no changes;
  full test suite passes **375 tests**.

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

### Step 5 — `docs: update TODO, CURRENT_TASK, and CHANGELOG for bank feed independence`
- Added Bank feed independence section to `docs/TODO.md`.
- Marked `CURRENT_TASK.md` as complete with final verification (379 tests pass).
- Migration fix: added `core/migrations/0002_banktransaction_source.py` so existing
  databases that applied the original squashed `0001_initial` migration safely gain
  the `source` column without data loss.

### Step 6 — `refactor(bank-feed): remove CSV bank importer after scope change`
- Deleted `core/engines/bank_feed_import.py` and removed `import_bank_feed_from_csv`
  from `core/engines/__init__.py`.
- Deleted `core/management/commands/import_bank_feed.py`.
- Removed `import_bank_feed_view` and `POST /dashboard/bank-feed/import/` from
  `core/views.py` and `core/urls.py`.
- Removed the dashboard CSV upload form from `core/templates/core/dashboard_content.html`.
- Deleted `core/tests/test_bank_feed_import.py` and all CSV-import tests in
  `core/tests/test_management.py` and `core/tests/test_views.py`.
- Kept `BankTransaction.source` and `BankTransactionSource` choices, synthetic
  generator relabeling, and independent simulator scenarios intact.
- Updated `docs/TODO.md`, `docs/CURRENT_TASK.md`, and `docs/CHANGELOG.md` to
  reflect the scope change.
- Final verification: `makemigrations --check --dry-run` reports no changes;
  full test suite passes 361 tests.
