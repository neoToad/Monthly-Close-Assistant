# Current Task

ConnectWise Step 1 — Models and migration

Actively working on:
- Adding `QBCustomer`, `Invoice`, `InvoiceLine`, `ConnectWiseCompany`, `ClientMapping`, `ConnectWiseWorkRole`, `TimeEntry`, `ExpenseEntry`, and `ProductEntry` models.
- Extending `FlagType` with ConnectWise-specific flag types.
- Updating the squashed migration `core/migrations/0001_initial.py` to include all new tables.
- Writing model tests first (TDD) in `core/tests/test_connectwise_models.py`.

Blockers or decisions:
- None.

Next step:
- After tests pass and `makemigrations --check --dry-run` reports no changes, commit and move to Step 2 (QBO customer/invoice sync).
