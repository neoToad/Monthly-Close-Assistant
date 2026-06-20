# Current Task

ConnectWise Step 3 — Synthetic ConnectWise feed

Actively working on:
- Create JSON fixtures under `core/fixtures/connectwise_scenarios/` for hourly leakage, flat-fee profitable, flat-fee margin erosion, flat-fee loss, missing mapping, and mixed scenarios.
- Implement `core/engines/connectwise_feed.py::generate_connectwise_feed(month, realm_id, scenario, force=False, seed=None)`.
- Add `core/management/commands/generate_connectwise_feed.py`.
- Write failing tests first in `core/tests/test_connectwise_feed.py`.

Blockers or decisions:
- None.

Next step:
- Write failing tests, then implement fixtures and the generator.
