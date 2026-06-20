# Current Task

Step 5 — ConnectWise reconciliation management command — IN PROGRESS.

Status:
- Step 4 (reconciliation engine) is complete and verified; 8 tests pass.
- Now adding `core/management/commands/run_connectwise_reconciliation.py` that calls
  `run_connectwise_reconciliation` and prints a summary.
- Will add command tests to `core/tests/test_management.py`.

Next:
- Implement the command following the existing bank-feed/reconciliation command patterns.
- Confirm it prints clients checked, unbilled flags, margin flags, and missing mappings.
- Run tests, then proceed to Step 6 (dashboard section).
