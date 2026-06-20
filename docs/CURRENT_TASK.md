# Current Task

Bank feed independence — Step 4: add independent simulator scenarios to the bank feed generator.

Status:
- Implementing `docs/plans/independent_bank_feed_plan.md` on `feature/close-assistant-build`.
- Step 1 committed: `BankTransaction.source` field and synthetic tracking.
- Step 2 committed: CSV import engine.
- Step 3 committed: `import_bank_feed` command, dashboard view, relabeled synthetic button,
  and CSV upload form.

Active work:
- Create `core/fixtures/` package and `core/fixtures/bank_feed_scenarios/independent_default.json`.
- Extend `generate_bank_feed` in `core/engines/bank_feed.py` with `scenario` and `scenario_file` arguments.
  - `derived` (default): existing behavior.
  - `independent`: generate rows from the fixture, randomize dates within the month,
    apply discrepancies, mark `source=synthetic`.
- Update `core/management/commands/generate_bank_feed.py` with `--scenario` and `--scenario-file`.
- Add command tests for `independent` and custom scenario files.

Next step:
- Run the full test suite, then commit.
- Step 5 will update docs (TODO, CURRENT_TASK, CHANGELOG) and run final verification.
