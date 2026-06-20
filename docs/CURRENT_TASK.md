# Current Task

No active bank-feed task — scope revised and committed.

Status:
- CSV bank importer removed from the bank-feed independence implementation.
- `BankTransaction.source`, synthetic generator relabeling, and independent
  simulator scenarios remain in place on `feature/close-assistant-build`.
- Commit `9bb33c5` records the removal.
- Final verification:
  - `docker compose exec web python manage.py makemigrations --check --dry-run` — no changes.
  - `docker compose exec web python manage.py test -v 2` — **361 tests pass**.

Kept deliverables:
- `BankTransaction.source` field with `BankTransactionSource` choices; synthetic
  generator marks rows as `synthetic`.
- Independent simulator scenario fixture, `--scenario` / `--scenario-file` support
  in `generate_bank_feed`, and command/view tests.
- Dashboard button relabeled "Generate Synthetic Bank Feed" with testing-only subtitle.

Removed deliverables:
- `core/engines/bank_feed_import.py` and `import_bank_feed_from_csv` export.
- `core/management/commands/import_bank_feed.py`.
- `core/tests/test_bank_feed_import.py` and all CSV-import view/command tests.
- `import_bank_feed_view`, `POST /dashboard/bank-feed/import/`, and dashboard
  CSV upload form.

Next work:
- Pick the next TODO item or plan; no further bank-feed independence work in scope.
