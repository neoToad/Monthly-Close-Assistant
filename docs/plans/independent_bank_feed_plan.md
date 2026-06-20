# Plan: Make the Bank Feed Independent of the QuickBooks GL

**Status:** Draft / ready for implementation  
**Date:** 2026-06-20  

## Goal

Separate the bank-feed side of reconciliation from the QuickBooks GL side so the system accurately models production: bank transactions arrive from their own source (CSV upload, bank API, or manual entry), while `generate_bank_feed` remains a clearly-labeled **testing-only simulator**.

This plan implements the three recommendations from the 2026-06-20 review:

1. Clarify that `generate_bank_feed` is a synthetic bank-feed **simulator**, not a data source.
2. Add a real CSV import path for `BankTransaction` rows so the production workflow is represented.
3. Let the simulator optionally create bank rows from realistic, **independent** fixtures rather than deriving them from the GL.

## Problem statement

Today `generate_bank_feed` (and the matching dashboard button) creates `BankTransaction` rows by mutating existing `Transaction` records. That is useful for deterministic regression tests, but it also:

* Makes the bank side look like a copy of the GL side, which hides real-world matching problems.
* Leaves no source lineage on `BankTransaction`, so it is impossible to tell whether a bank row came from a simulator, CSV, bank API, or manual entry.
* Provides no path for importing a real bank statement into the reconciliation engine.

The underlying data model is already correct — `Transaction` and `BankTransaction` are separate tables with a nullable `matched_transaction_id` — but the tooling only exercises the synthetic/derived path.

## Proposed changes

### 1. Add `source` tracking to `BankTransaction`

Add a `source` field so every bank row records how it entered the system.

```python
class BankTransactionSource(models.TextChoices):
    SYNTHETIC = "synthetic", "Synthetic (test simulator)"
    CSV_IMPORT = "csv_import", "CSV import"
    BANK_FEED_API = "bank_feed_api", "Bank feed API"
    MANUAL = "manual", "Manual entry"
```

* Update `BankTransaction` to store `source` with default `BankTransactionSource.CSV_IMPORT` for new imports and `MANUAL` for direct creation.
* Update `core/engines/bank_feed.py` to set `source=BankTransactionSource.SYNTHETIC` on every generated row.
* Update existing `_make_bank_txn` helper and any tests that create `BankTransaction` directly to pass a source or accept the new default.

### 2. Clarify the synthetic generator as a simulator

* Rename the dashboard button from **"Generate Bank Feed"** to **"Generate Synthetic Bank Feed"** and add a small help line explaining it is for testing.
* Update `core/management/commands/generate_bank_feed.py` help text to begin with "(Testing/simulator only)".
* Update the module docstrings in `core/engines/bank_feed.py` and the command to call the tool a "bank feed simulator".
* Keep the existing command name and URL to avoid breaking current tests; only labels and docstrings change.

### 3. Add a real CSV import path for bank transactions

Create a production-oriented import that reads a bank statement CSV and writes `BankTransaction` rows.

#### 3.1 Engine

New module `core/engines/bank_feed_import.py` with:

```python
def import_bank_feed_from_csv(
    csv_file,
    month: str,
    realm_id: str,
    force: bool = False,
    source: str = BankTransactionSource.CSV_IMPORT,
) -> dict:
    """Read a bank statement CSV and create BankTransaction rows.

    Required CSV columns: date, amount
    Optional columns: vendor, category, gl_account, external_id, description
    """
```

Validation:

* `date` must be parseable (`YYYY-MM-DD`, `MM/DD/YYYY`, `DD-MM-YYYY`).
* `amount` must be a valid decimal.
* If `month` is provided, every row's date must fall inside that month.
* At least one data row is required.

Idempotency:

* By default, raise `ValueError` when `BankTransaction` rows already exist for `(company, month)`.
* With `force=True`, delete existing rows for the month before import (same pattern as `generate_bank_feed`).
* Future enhancement: deduplicate by `external_id` when the column is present; out of scope for this plan.

#### 3.2 Management command

New `core/management/commands/import_bank_feed.py`:

```bash
python manage.py import_bank_feed 2025-01 \
    --realm-id realm-a \
    --csv path/to/bank.csv \
    [--force]
```

#### 3.3 Dashboard view

New view `import_bank_feed_view` wired to `POST /dashboard/bank-feed/import/`.

* Accept a multipart form with `month`, `realm_id`, and `csv_file`.
* Validate file size and type (CSV only).
* Return the dashboard content partial with a notice, mirroring `generate_bank_feed_view`.
* Add an "Import Bank Feed CSV" form to `dashboard_content.html`, placed next to the synthetic generator button.

### 4. Make the simulator optionally create independent bank rows

Extend `core/engines/bank_feed.py` so it can produce bank rows that are not direct mutations of GL transactions.

#### 4.1 Preset scenarios

Add a `--scenario` argument to `generate_bank_feed`:

* `derived` (default) — current behavior: read `Transaction` rows and mutate them.
* `independent` — generate bank rows from a built-in fixture of realistic bank descriptions (e.g. `"POS DEBIT ACME CORP #1234"`, `"ACH DEPOSIT CUSTOMER PAYMENT"`, `"MONTHLY SERVICE FEE"`).

The `independent` scenario:

* Ignores existing `Transaction` rows as the base set (but still respects `cash_only` if provided).
* Creates a realistic mix of debits and credits spread across the month.
* Applies the same discrepancy rates (`drop_rate`, `dup_rate`, `amount_shift_rate`, `date_shift_rate`, `extra_rate`) so the reconciliation engine still has meaningful work.
* Marks all rows `source=BankTransactionSource.SYNTHETIC`.

#### 4.2 Scenario fixtures

Add `core/fixtures/bank_feed_scenarios/independent_default.json`:

```json
[
  {
    "vendor": "POS DEBIT ACME CORP #1234",
    "amount": "125.00",
    "category": "Office Supplies",
    "gl_account": "5000 - Supplies"
  },
  ...
]
```

Create the `core/fixtures/` package. Fixtures contain template rows; the engine randomizes dates within the target month and applies discrepancy rates.

#### 4.3 Custom scenario file

Add `--scenario-file path/to/scenario.json` so tests can load arbitrary independent bank feeds.

### 5. Update the reconciliation engine

`core/engines/reconciliation.py` does not need structural changes, but it should:

* Continue matching on vendor, amount, and date.
* Optionally log a warning when a synthetic bank row and a GL row share the same `qb_transaction_id` but differ in amount/date, since that indicates a simulator discrepancy.

No matching-engine enhancements (e.g. fuzzy vendor matching) are in scope; the current exact matcher is sufficient to exercise the new source-lineage and import paths.

## Files touched

### New files

* `core/engines/bank_feed_import.py`
* `core/management/commands/import_bank_feed.py`
* `core/fixtures/__init__.py`
* `core/fixtures/bank_feed_scenarios/__init__.py`
* `core/fixtures/bank_feed_scenarios/independent_default.json`
* `core/tests/test_bank_feed_import.py`

### Modified files

* `core/models.py` — add `BankTransaction.source` field; update `BankTransaction.__str__` if useful.
* `core/migrations/0001_initial.py` — include the new `source` column in the squashed migration.
* `core/engines/bank_feed.py` — set `source=synthetic`, add `--scenario` and `--scenario-file` support.
* `core/engines/__init__.py` — export `import_bank_feed_from_csv`.
* `core/management/commands/generate_bank_feed.py` — new `--scenario` / `--scenario-file` arguments; updated help text.
* `core/views.py` — add `import_bank_feed_view`; update `generate_bank_feed_view` notice text; update `generate_bank_feed_view` to pass `source`.
* `core/urls.py` — add `path("dashboard/bank-feed/import/", views.import_bank_feed_view, name="import_bank_feed")`.
* `core/templates/core/dashboard_content.html` — relabel the synthetic button; add CSV upload form.
* `core/tests/test_management.py` — update `GenerateBankFeedCommandTests` for `source=synthetic`; add tests for `import_bank_feed` command; add independent scenario tests.
* `core/tests/test_views.py` — update `GenerateBankFeedViewTests` for relabeled button; add upload view tests.
* `docs/TODO.md` — add a "Bank feed independence" section.
* `docs/CURRENT_TASK.md` — reflect the active work.
* `docs/CHANGELOG.md` — summarize the new import path, source tracking, and simulator scenarios.

## Migration

Because the app is pre-production and migrations were recently squashed into `core/migrations/0001_initial.py`, edit the squashed migration directly to add:

```python
source = models.CharField(
    max_length=20,
    choices=BankTransactionSource.choices,
    default=BankTransactionSource.MANUAL,
    help_text="How this bank transaction entered the system.",
)
```

After editing, run:

```bash
docker compose exec web python manage.py makemigrations --check --dry-run
```

to confirm no new migration is generated.

## Test plan

1. **Model tests**
   * `BankTransaction` defaults to `source=manual` when created directly.
   * Synthetic generator sets `source=synthetic`.
   * CSV import sets `source=csv_import`.

2. **CSV import engine tests** (`core/tests/test_bank_feed_import.py`)
   * Import creates rows from a well-formed CSV.
   * Missing required column raises `ValueError`.
   * Amount/date parsing errors are collected and reported.
   * Date outside the target month raises `ValueError`.
   * Import without `--force` errors when rows already exist.
   * `--force` replaces existing rows for the month.

3. **Management command tests**
   * `import_bank_feed` command succeeds with a sample CSV.
   * `import_bank_feed` command reports validation errors.
   * `generate_bank_feed --scenario independent` creates rows not derived from GL.
   * `generate_bank_feed --scenario derived` keeps existing behavior.
   * `generate_bank_feed --scenario-file custom.json` loads a custom fixture.

4. **View tests**
   * Dashboard shows the relabeled "Generate Synthetic Bank Feed" button.
   * Dashboard shows the "Import Bank Feed CSV" form.
   * Uploading a CSV via `import_bank_feed_view` creates rows and refreshes the dashboard.
   * Uploading an invalid CSV returns a 400 with a clear notice.

5. **Reconciliation integration**
   * Running reconciliation after a CSV import produces the expected flags for mismatches and one-sided rows.

## UI/UX changes

In `core/templates/core/dashboard_content.html`:

1. Relabel the existing form button to **"Generate Synthetic Bank Feed"**.
2. Add a short subtitle: "For testing only — creates fake bank rows from GL data or a scenario fixture."
3. Add a new form next to it:
   * File input for `.csv` files.
   * Button **"Import Bank Feed CSV"**.
   * Subtitle: "Load real bank statement transactions for reconciliation."

## Risks and open decisions

| Risk | Mitigation |
|---|---|
| Editing the squashed migration directly could drift from model state. | Run `makemigrations --check --dry-run` after the change. |
| Fuzzy bank descriptions won't match GL vendors with the current matcher, making the `independent` scenario produce only unmatched flags. | Acceptable for this increment; the scenario is still useful for testing the engine and source lineage. Document that fuzzy vendor matching is a future enhancement. |
| Large CSV uploads could block the request. | Add a size limit in the view (e.g. 5 MB) and consider streaming/chunked import later. |
| `BankTransaction.source` default choice may conflict with future bank API imports. | Use `manual` as the safe default for direct ORM creation; imports explicitly set `csv_import`. |

## Commit plan

1. `feat(models): add BankTransaction.source field and synthetic source tracking`
   * Add field, update migration, update generator, update existing tests/helpers.
2. `feat(engines): add CSV import engine for BankTransaction rows`
   * `core/engines/bank_feed_import.py`, `core/tests/test_bank_feed_import.py`.
3. `feat(management): add import_bank_feed command and dashboard view`
   * Command, view, URL, template changes, view tests.
4. `feat(engines): add independent bank-feed scenarios to simulator`
   * `--scenario`, `--scenario-file`, fixture files, command tests.
5. `docs: update TODO, CURRENT_TASK, and CHANGELOG`

## Verification

* `docker compose exec web python manage.py makemigrations --check --dry-run` reports no changes.
* `docker compose exec web python manage.py test -v 2` passes with new tests included.
* Manual smoke test:
  1. Sync QuickBooks transactions.
  2. Import a sample bank CSV.
  3. Run reconciliation and confirm flags are created.
  4. Generate a synthetic feed with `--scenario independent` and confirm rows are created with `source=synthetic`.