# Monthly Close Assistant - Refactor Plan

**Status:** Completed
**Date completed:** 2026-06-19

## Completed Scope

- Reorganized domain code into `core/agents`, `core/engines`, and `core/services`.
- Kept `core/models.py` as a single Django module.
- Centralized common dates, constants, retry/backoff, QuickBooks write helpers, and posted-total computation.
- Extracted account-reconciliation apply orchestration into `core/services/reconciliation.py`.
- Added `core/services/close_summary.py` so views and commands can fetch optional QuickBooks GL totals outside the agent layer.
- Added high-priority type hints and docstrings across views, agents, engines, QuickBooks helpers, and services.
- Improved OAuth callback error handling with configuration-specific responses and contextual logging.
- Added structured Celery task logging with task id context and re-raise behavior.
- Added reconcile apply failure-mode tests for partial QuickBooks writes and post-apply sync failures.
- Squashed app migrations into `core/migrations/0001_initial.py`.

## Naming Decisions

- Keep `QBAccount.account_id` rather than renaming to `qb_account_id`.
  - Reason: `QBAccount` is already scoped to QuickBooks, and the field is documented as the external QuickBooks account id.
  - Public function parameters and balance/state models continue to use `qb_account_id` where ambiguity exists.
- Keep `Transaction.gl_account` rather than renaming to `gl_account_name`.
  - Reason: the field is already documented as the GL account name and is used broadly in tests, normalization, and reconciliation queries.
  - A schema rename would add churn without changing behavior now that the squashed migration is stable.
- Keep `realm_id` on realm-scoped rows as a denormalized filter while `company` remains the canonical relational scope.

## Verification

- `docker compose exec web python manage.py test -v 2` passes: 295 tests.
- `docker compose exec web python manage.py makemigrations --check --dry-run` reports no changes.

## Recommended Next Step

All items from the previous Recommended next step are complete:

1. Finalize naming/migration decisions.
2. Finish high-priority type hints and docstrings.
3. Add targeted failure-mode tests for reconcile apply flows.
4. Perform migration squash after the model/package layout stabilized.

## Remaining Future Questions

- Whether to extract duplicated LLM provider plumbing into a dedicated `core/services/llm.py`.
- Whether `seed_bank_balances --force` should change behavior or be removed.
- Whether future production hardening should add full audit logging, RBAC, and operational observability beyond the current portfolio scope.
