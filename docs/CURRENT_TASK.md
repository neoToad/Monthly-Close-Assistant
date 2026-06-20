# Current Task

Step 4 — ConnectWise reconciliation engine — IN PROGRESS.

Status:
- Step 1 (models), Step 2 (QBO sync), and Step 3 (synthetic feed) are complete and verified.
- Now implementing `core/engines/connectwise_reconciliation.py::run_connectwise_reconciliation(month, realm_id=None)`.
- Goal: per `(company, connectwise_company)` in the target month, flag `CONNECTWISE_UNBILLED`, `CONNECTWISE_MARGIN`, and `CONNECTWISE_MISSING_MAPPING` as defined in the plan.
- Existing tests in `core/tests/test_connectwise_reconciliation.py` should drive the implementation (TDD).

Next:
- Confirm the existing tests fail for the expected reason (missing engine).
- Write the minimum engine code to make tests pass.
- Proceed to Step 5 (management command), Step 6 (dashboard section), and Step 7 (docs/verification).
