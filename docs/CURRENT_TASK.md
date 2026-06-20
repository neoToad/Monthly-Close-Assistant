# Current Task

Bank feed independence — Step 1: add `BankTransaction.source` field and synthetic source tracking.

Status:
- Implementing `docs/plans/independent_bank_feed_plan.md` on `feature/close-assistant-build`.
- Currently working on the first commit: adding `BankTransactionSource` choices, the `source`
  column on `BankTransaction`, editing the squashed migration, and updating the synthetic
  generator + tests to set `source=synthetic`.

Active work:
- Write failing model/engine tests for source tracking.
- Add the field and migration change.
- Wire `source=BankTransactionSource.SYNTHETIC` through `core/engines/bank_feed.py`.
- Update `core/tests/test_management.py` helpers and existing assertions.

Next step:
- Run the test suite to confirm the source-tracking changes pass, then commit.
- Step 2 will add the CSV import engine.
