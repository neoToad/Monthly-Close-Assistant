# Current Task

Step 3 — Synthetic ConnectWise feed — COMPLETE and verified.

Status:
- All six JSON fixtures created under `core/fixtures/connectwise_scenarios/`.
- `core/engines/connectwise_feed.py::generate_connectwise_feed` implemented with idempotent upserts, `--force`, and `--seed` support.
- `core/management/commands/generate_connectwise_feed.py` added.
- `core/tests/test_connectwise_feed.py` covers scenario counts, flat-fee mappings, missing mappings, mixed scenarios, force/idempotency, and seed reproducibility (9 tests passing).

Paused as requested; not starting Step 4.

Next step when work resumes:
- Step 4 — ConnectWise reconciliation engine: implement `core/engines/connectwise_reconciliation.py::run_connectwise_reconciliation(month, realm_id=None)` with unbilled, margin, and missing-mapping flags, plus tests in `core/tests/test_connectwise_reconciliation.py`.
