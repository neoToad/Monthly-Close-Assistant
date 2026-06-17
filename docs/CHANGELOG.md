# Changelog

All notable changes to the Monthly Close Assistant are recorded here, one entry per
commit, per the AGENTS.md workflow. Steps track the prompts in
`docs/Monthly_Close_Assistant_CLI_Agent_Prompts_Full.md`.

## Environment note (applies to the Foundation stage)

The build environment has Python 3.14.2 with no project packages pre-installed, and
PostgreSQL 17 & 18 running locally as Windows services whose superuser credentials are
not available to the build agent. To satisfy "write & apply migrations" and "run the
test suite" (both required by TDD), a self-contained PostgreSQL 17 instance is
provisioned in Docker on port **5434** (`close_pg` container, db `close_assistant`,
user `close_app`). This does not touch the user's local PG 17/18 services and is fully
reversible:

```
docker stop close_pg && docker rm close_pg   # tear down
docker start close_pg                         # restart later
```

This is a documented deviation from "use the running local Postgres"; it is still a
real Postgres reachable at `localhost`, so migrations and tests exercise the actual
Postgres engine (not SQLite).

---

## Step 1 — `feat(core): step 1 — Django project scaffold with Postgres + HTMX`

Scaffolded the `close_assistant` Django project with a `core` app at the repo root,
configured PostgreSQL from environment variables (DB_NAME, DB_USER, DB_PASSWORD,
DB_HOST, DB_PORT) via python-decouple, wired django-htmx into INSTALLED_APPS +
`HtmxMiddleware` and a `core/templates/base.html`, and wrote `.env.example` listing
every required variable. Default migrations applied to Postgres, confirming
connectivity. 11 scaffold tests pass (`python manage.py test`).

**TDD:** wrote `core/tests/test_scaffold.py` first and confirmed it failed for the
right reasons (default sqlite engine, `core`/`django_htmx` absent from INSTALLED_APPS,
`HtmxMiddleware` missing, `base.html` not found), then implemented to green.

**Improvements beyond the spec:**
- `requirements.txt` pinning the top-level deps (Django 6.0.6, python-decouple 3.8,
  django-htmx 1.27.0, psycopg[binary] 3.3.4, python-quickbooks 0.9.12,
  intuit-oauth 1.2.6).
- Tests split into a `core/tests/` package (per AGENTS.md) with a dedicated
  `test_scaffold.py`; DB-field tests use `.get()` so the pre-implementation sqlite
  scaffold fails with clean AssertionErrors instead of KeyErrors.
- `base.html` ships a small, dependency-free internal-tool stylesheet (table, flash,
  button styles) plus `content`/`extra_head`/`scripts` blocks for later HTMX partials.
- `DEFAULT_AUTO_FIELD` set explicitly to `BigAutoField`; `STATIC_ROOT` added for a
  later collectstatic stage.
- Module docstrings + `from __future__ import annotations` in settings and tests.

**Deviations:**
- Postgres runs in a Docker container (`close_pg`) on host port **5434**, not the
  machine's local PG services. Local PG 17 & 18 bind host 5432 & 5433, so a Docker
  container on 5433 collided (`localhost:5433` routed to the local PG and failed
  auth); 5434 is free. See the environment note at the top of this file.
- `startproject` was run in a temp dir and moved into the repo root because Django
  aborts `startproject <name> .` on a non-empty target directory.
- Used psycopg3 (`psycopg[binary]`) instead of psycopg2; Django 6.0 supports it
  natively and it has Python 3.14 wheels.

---

## Step 2 — `feat(core): step 2 — Postgres schema: Transaction/BankTransaction/Flag/CloseSummary + admin`

Added the four `core` models with field shapes per the spec:

- **Transaction** — date, vendor, amount `DecimalField(12,2)`, category, gl_account,
  `qb_transaction_id` (unique + indexed, the idempotent-sync natural key), source_type
  (choices: Purchase / Deposit / JournalEntry).
- **BankTransaction** — mirrors the Transaction shape, plus a nullable
  `matched_transaction_id` FK → Transaction (`on_delete=SET_NULL`).
- **Flag** — flag_type (reconciliation / anomaly), nullable FKs to Transaction and to
  BankTransaction, reason `TextField`, severity (low/medium/high), status
  (open/approved/rejected), created_at.
- **CloseSummary** — month (YYYY-MM, unique), summary_text, status (draft/reviewed),
  reviewer_notes, created_at.

Wrote and applied migration `core.0001_initial`. Registered all four in Django admin.

**TDD:** wrote `core/tests/test_models.py` (17 tests) first and confirmed it failed for
the right reason (`ImportError` — models undefined), then implemented to green. Full
suite: 28 tests pass; the Postgres test DB is created/dropped by the runner.

**Improvements beyond the spec:**
- `TextChoices` enums for source_type, flag_type, severity, Flag status, and
  CloseSummary status (forward-compatible with the reconciliation/anomaly prompts).
- Money stored as `DecimalField(max_digits=12, decimal_places=2)`, not float.
- `help_text` on every meaningful field; class docstrings;
  `from __future__ import annotations`.
- `CloseSummary.month` validated with `RegexValidator(r"^\d{4}-\d{2}$")` + unique;
  `verbose_name_plural` set.
- Admin tuned for reviewers: `list_display`, `list_filter`, `search_fields`,
  `date_hierarchy` (token fields excluded from QBToken admin in Step 3).
- `__str__` on every model.
- Hardened `test_scaffold.test_db_name_from_env` against the test runner's `test_` DB
  name prefix (surfaced when the full suite first ran alongside the model TestCases).

**Deviations:** None. The schema matches the spec; the choice sets for flag_type /
severity / status anticipate the reconciliation (Prompt 7) and anomaly (Prompt 8)
prompts that create Flags of those types.