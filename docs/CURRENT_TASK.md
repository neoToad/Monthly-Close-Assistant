# Current Task

Bank feed independence — Step 2: build the CSV import engine for ``BankTransaction`` rows.

Status:
- Implementing `docs/plans/independent_bank_feed_plan.md` on `feature/close-assistant-build`.
- Step 1 is committed: `BankTransaction.source` field exists, generator marks rows
  as `synthetic`, and model/command tests pass.

Active work:
- Create `core/engines/bank_feed_import.py` with `import_bank_feed_from_csv`.
- Support required `date`/`amount` columns plus optional vendor/category/gl_account/
  external_id/description.
- Validate date formats (YYYY-MM-DD, MM/DD/YYYY, DD-MM-YYYY), amount parsing, and
  month containment.
- Enforce idempotency: raise when rows already exist for the month unless `force=True`.
- Add `core/tests/test_bank_feed_import.py` covering happy path, validation errors,
  out-of-month dates, and force overwrite.

Next step:
- Run the CSV import engine tests, then commit.
- Step 3 will wire the `import_bank_feed` management command and dashboard view.
