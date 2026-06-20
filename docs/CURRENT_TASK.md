# Current Task

Bank feed independence — COMPLETE.

Status:
- All four steps from `docs/plans/independent_bank_feed_plan.md` are implemented
  and verified on `feature/close-assistant-build`.
- Final verification:
  - `docker compose exec web python manage.py makemigrations --check --dry-run` — no changes.
  - `docker compose exec web python manage.py test -v 2` — **379 tests pass**.

Completed deliverables:
- Step 1: `BankTransaction.source` field with `BankTransactionSource` choices; synthetic
  generator marks rows as `synthetic`; migration and model/command tests updated.
- Step 2: CSV import engine `core/engines/bank_feed_import.py` with date/amount validation,
  month containment, idempotency, and `force` overwrite.
- Step 3: `import_bank_feed` management command, dashboard view, URL, CSV upload form,
  relabeled synthetic generator button, and view/command tests.
- Step 4: Independent simulator scenario fixture, `--scenario` / `--scenario-file` support
  in `generate_bank_feed`, and command tests.
- Step 5: `docs/TODO.md`, `docs/CHANGELOG.md`, and this file updated.
- Fix: added `core/migrations/0002_banktransaction_source.py` to safely add the
  `source` column on databases that had already applied the original squashed
  `0001_initial` migration.

Next work:
- No further bank-feed independence work in this plan. Pick the next TODO item or plan.
