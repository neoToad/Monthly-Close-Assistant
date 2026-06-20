# Current Task

Bank feed independence — Step 3: add `import_bank_feed` command and dashboard view.

Status:
- Implementing `docs/plans/independent_bank_feed_plan.md` on `feature/close-assistant-build`.
- Step 1 is committed: `BankTransaction.source` field exists, generator marks rows
  as `synthetic`.
- Step 2 is committed: `core/engines/bank_feed_import.py` with full test coverage.

Active work:
- Create `core/management/commands/import_bank_feed.py`.
- Add `import_bank_feed_view` in `core/views.py` and wire `POST /dashboard/bank-feed/import/`.
- Validate file size/type in the view and return the dashboard content partial with notices.
- Update `dashboard_content.html`:
  - Relabel synthetic generator button and add testing-only subtitle.
  - Add "Import Bank Feed CSV" multipart form with file input.
- Add view tests and command tests for the new import path.

Next step:
- Run the full test suite for this step, then commit.
- Step 4 will add independent simulator scenarios.
