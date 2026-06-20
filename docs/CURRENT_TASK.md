# Current Task

Implement `docs/plans/seed_demo_msp_data_plan.md` — add a management command that seeds the local database with realistic MSP demo data for dashboard and reconciliation demos.

**Status:** Complete and committed (`025c6d6`)

**What was built:**
- Added `core/fixtures/msp_demo_data.py` with the chart of accounts, customers, vendors, and transaction fixtures for **Next Level Networks Demo**.
- Added `core/management/commands/seed_demo_msp_data.py` supporting `YYYY-MM`, `--realm-id` (default `demo-msp`), `--force`, `--include-bank-feed`, and `--seed`.
- Added `core/tests/test_seed_demo_msp_data.py` with 14 tests covering company/account creation, transaction counts, bank statement balance, idempotency, force re-seed, bank-feed integration, balance-reconciliation flags, and new-vendor anomaly flags.
- Updated `docs/TODO.md`, `docs/CHANGELOG.md`, and this file.

**Verification:**
- `docker compose exec web python manage.py test core.tests.test_seed_demo_msp_data -v 2` — 14 tests pass.
- `docker compose exec web python manage.py test -v 2` — **375 tests pass**.
- `docker compose exec web python manage.py makemigrations --check --dry-run` — no changes.

**Next step:**
- Pick the next TODO item or plan.
