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

---

## Step 3 — `feat(core): step 3 — QuickBooks OAuth 2.0 + sync_quickbooks command`

Implemented the QuickBooks Online OAuth 2.0 authorization-code flow and a
`sync_quickbooks` management command, test-first against **mocked** QuickBooks
responses (no live sandbox credentials).

- **OAuth start view** (`/quickbooks/oauth/start/`) — builds an Intuit `AuthClient`
  from `QB_CLIENT_ID`/`QB_CLIENT_SECRET`/`QB_REDIRECT_URI`, generates a CSRF state,
  stashes it in the session, and redirects to Intuit's authorize URL.
- **OAuth callback view** (`/quickbooks/oauth/callback/`) — verifies the state,
  exchanges the code for tokens, and persists them.
- **Token-refresh helper** (`refresh_tokens`) — drives `AuthClient.refresh()` and
  returns the new tokens with computed access/refresh expiry datetimes.
- **`sync_quickbooks` command** — authenticates with the stored token, pulls
  Purchase / Deposit / JournalEntry, normalizes each into `Transaction`, and skips
  records already present (matched on `qb_transaction_id`).

**TDD:** wrote `core/tests/test_quickbooks.py` (encryption roundtrip + plaintext
fallback, per-type normalization, skip-on-missing-id/date, idempotent sync,
token-refresh) and `core/tests/test_views.py` (OAuth start redirect + state,
callback exchange/store, state mismatch, missing code, sync command happy path +
no-token error) first; confirmed both modules failed to import for the right reason
(`ModuleNotFoundError: core.quickbooks`), then implemented to green. Full suite:
**46 tests pass**.

**Improvements beyond the spec:**
- DRY service split into `core/quickbooks/client.py` (OAuth, refresh, pull,
  normalize, sync) and `core/quickbooks/tokens.py` (Fernet encrypt/decrypt + token
  persistence) — suggested by the foundation prompt.
- `QBToken` model stores access/refresh tokens **encrypted at rest** with a Fernet
  key (`QB_TOKEN_ENCRYPTION_KEY` env), with a plaintext dev fallback that emits a
  warning. Migration `core.0002_qbtoken`; admin excludes the token fields from view.
- Idempotent sync keyed on the natural key `qb_transaction_id` (`get_or_create`),
  with a per-type counts summary (`created`/`skipped`/`errors`/`per_type`).
- Defensive normalization: tolerant date parsing, `Decimal(str(...))` for money,
  best-effort `Ref.name`/`Ref.value` lookups, and skip (not crash) on records missing
  an id or date.
- `intuit-oauth` is imported via its `intuitlib` namespace (`intuitlib.client.AuthClient`,
  `intuitlib.enums.Scopes`) — the package's `intuit_oauth` shim is broken on Python 3.14
  (see project memory).
- Intuit `environment` hardcoded to `"sandbox"` (matches
  `quickbooks.client.Environments.SANDBOX == 'sandbox'`); `QB_ENVIRONMENT` is
  formalized in Prompt 4.

---

## Step 4 — `feat(core): step 4 — QuickBooks env config, sandbox/production switch`

Hardened QuickBooks environment configuration and token-refresh buffer settings.

- **`.env.example`** now documents every QuickBooks variable:
  `QB_CLIENT_ID`, `QB_CLIENT_SECRET`, `QB_REDIRECT_URI`, `QB_SANDBOX_COMPANY_ID`,
  `QB_ENVIRONMENT` (sandbox|production), `QB_TOKEN_REFRESH_BUFFER_MINUTES`, and
  `QB_TOKEN_ENCRYPTION_KEY`. Each variable has a comment explaining where it comes
  from and what value to use for local development.
- **`close_assistant/settings.py`** added `QB_ENVIRONMENT` and
  `QB_TOKEN_REFRESH_BUFFER_MINUTES` settings, loaded via `python-decouple`.
- **`core/quickbooks/client.py`** added `get_environment()` (validates
  sandbox|production, case-insensitive, defaults to sandbox) and `get_api_base_url()`
  returning the correct v3 API base URL for each environment.
- **`make_auth_client` / `build_quickbooks_client`** now read `QB_ENVIRONMENT` from
  settings, so the OAuth and data clients both target the configured QuickBooks
  environment (sandbox or production).
- **`QBToken.is_access_token_expired()`** now accepts a `buffer_minutes` argument
  defaulting to `QB_TOKEN_REFRESH_BUFFER_MINUTES`. Tokens inside that buffer are
  treated as expired so the sync can refresh proactively before Intuit rejects the
  request.

**TDD:** extended `core/tests/test_quickbooks.py` and `core/tests/test_scaffold.py`
with 9 new tests first: environment default/read/validation/case-normalization,
make_auth_client passes the configured environment, sandbox/production API base
URLs, and token-expiry buffer behavior. Confirmed failures (`AttributeError` for
new helpers, `AssertionError` for hardcoded sandbox), then implemented to green.
Full suite: **55 tests pass**.

**Improvements beyond the spec:**
- Centralized environment validation in `get_environment()` so the app fails fast
  with a clear `ValueError` on an invalid `QB_ENVIRONMENT` value.
- `get_api_base_url()` is exposed as a reusable helper for any future direct API
  calls (the python-quickbooks client already picks the right host via
  `AuthClient.environment`, but the explicit URL is useful for logging / links).
- `QBToken.is_access_token_expired()` preserves backward compatibility: calling it
  without arguments still uses the configured buffer from settings.

**Deviations:** None. The live QuickBooks sandbox pull remains un-exercised; this
step only changed configuration and unit-tested the environment switching logic.

---

## Step 5 — `feat(core): step 5 — QuickBooks sync retry, refresh, and clear logging`

Added robust error handling around the QuickBooks sync pipeline.

- **`refresh_and_store_tokens()`** in `core/quickbooks/client.py` builds a fresh
  `AuthClient` seeded with the stored refresh token, calls `refresh()`, and writes
  the new tokens back to `QBToken` via `store_tokens`.
- **`call_with_retry()`** wraps every QuickBooks API call:
  - Proactively refreshes the access token before the first attempt if it is expired
    or inside `QB_TOKEN_REFRESH_BUFFER_MINUTES`.
  - Catches `AuthorizationException` mid-sync, refreshes the token once, and retries.
  - Catches transient errors (`QuickbooksException`, `ConnectionError`, `TimeoutError`)
    and retries up to 3 times with exponential backoff (2s, 4s, 8s).
  - Logs every retry path and final failure clearly.
- **`pull_raw_records()`** now routes each object query through `call_with_retry`,
  passing the stored `QBToken` through.
- **`sync_transactions()`** catches final pull failures, returns an error summary
  (`errors=1`, `error_message`), and logs the exception instead of crashing silently.
- **`sync_quickbooks` command** surfaces any `error_message` as a `CommandError`.

**TDD:** added 5 new tests in `core/tests/test_quickbooks.py` for proactive refresh,
auth-error refresh+retry, auth-error-after-refresh failure, transient-error
exponential backoff, and transient-error success-on-retry. Confirmed failures for
missing helpers, then implemented to green. Full suite: **60 tests pass**.

**Improvements beyond the spec:**
- Wrapped the *entire* data-pull path in retry logic, not just the top-level sync
  command, so every `Purchase.all()` / `Deposit.all()` / `JournalEntry.all()` call
  is resilient.
- `sync_transactions()` returns an error result rather than crashing the command,
  keeping the management command in control of the final user-facing message.
- Used `time.sleep` directly in `call_with_retry` (patched to no-op in tests) so the
  backoff behavior is real in production but fast in the test suite.

**Deviations:** None. The live QuickBooks sandbox pull remains un-exercised; all
retry/refresh behavior is unit-tested with mocked exceptions.

---

## Step 6 — `feat(core): step 6 — fake bank feed generator with configurable discrepancies`

Built a fake bank feed generator for reconciliation testing.

- **New module `core/bank_feed.py`** with `generate_bank_feed(month, ...)`:
  - Reads ``Transaction`` records for the requested month.
  - Uses Pandas to apply configurable discrepancies:
    * ``drop_rate`` (default 5%)
    * ``dup_rate`` (default 3%)
    * ``amount_shift_rate`` (default 4%, deltas -$2.50 to +$3.75)
    * ``date_shift_rate`` (default 5%, ±1-2 days)
    * ``extra_rate`` (default 3%, bank-only rows with no GL match)
  - Returns and logs a discrepancy summary with counts for each category.
  - Rejects regeneration unless ``force=True``; ``force`` deletes existing bank rows
    for the month first.
- **New management command `generate_bank_feed``** with arguments for month and all
  five rates, plus ``--force`` and an optional ``--seed`` for reproducible testing.
- Added **Pandas 2.2.3** and **NumPy 2.2.6** to `requirements.txt`.

**TDD:** created `core/tests/test_management.py` with 4 tests first: no-data
warning, generation + summary output, ``--force`` overwrite behavior, and
month-isolation. Confirmed failures (`Unknown command: 'generate_bank_feed'`), then
implemented to green. Full suite: **64 tests pass**.

**Improvements beyond the spec:**
- Isolated the generator logic in `core/bank_feed.py` so it can be tested and reused
  outside the management command (e.g., from the upcoming `seed_demo_data` command).
- Used ``bulk_create`` inside an atomic transaction for efficient insertion.
- Added ``--seed`` for deterministic discrepancy generation, useful for reconciliation
  test assertions.
- Preserved bank data for other months by filtering deletes/lookups on the target
  month range.

**Deviations:** None.

---

## Step 7 — `feat(core): step 7 — Pandas reconciliation engine + run_reconciliation command`

Implemented the reconciliation engine that compares GL ``Transaction`` records to
the fake ``BankTransaction`` feed and creates ``Flag`` records for mismatches.

- **New package `core/reconciliation/`** with `engine.py`:
  - Loads both sides into Pandas DataFrames for the target month.
  - Matches bank rows to GL rows on vendor equality, amount within $0.01, and date
    within 1 day.
  - Flags amount mismatches, date mismatches (within tolerance), bank-only rows,
    and GL-only rows.
  - Returns a summary dict with counts of matched/unmatched rows and flags created.
- **New management command `run_reconciliation``** taking a `YYYY-MM` month argument
  and printing the reconciliation summary.

**TDD:** extended `core/tests/test_management.py` with 7 reconciliation tests first:
no-data exit, clean match (no flags), amount mismatch flag, date mismatch beyond
and within tolerance, missing bank, and missing GL. Confirmed failures (`Unknown
command: 'run_reconciliation'`), then implemented to green. Full suite: **71 tests pass**.

**Improvements beyond the spec:**
- Separated the matching engine (`core/reconciliation/engine.py`) from the command
  so the logic is reusable and unit-testable without invoking a management command.
- Used Pandas for the comparison and `bulk_create` for flag insertion.
- Matched on lower-cased vendor names to tolerate minor casing differences.

**Deviations:** None.

**Deviations:**
- **Live sandbox pull NOT exercised** (no sandbox credentials available). The OAuth
  flow and sync pipeline are fully implemented and unit-tested against mocked
  QuickBooks responses; the live pull against the Intuit sandbox is deferred and
  noted in `docs/TODO.md`. Per the foundation prompt's instruction, this is recorded
  here explicitly.
- Retry/backoff on QuickBooks API errors is deferred to Prompt 5.

---

## Step 8 — `feat(core): step 8 — rule-based anomaly detection integrated with reconciliation`

Added rule-based anomaly detection on a month's ``Transaction`` records and
wired it into the `run_reconciliation` command.

- **New package `core/anomaly/`** with `rules.py`:
  - Vendor amounts more than 2 standard deviations from that vendor's historical
    average (or outside a constant historical average when σ = 0).
  - Duplicate transactions (same vendor + amount within a 7-day window).
  - New vendors with no transaction history before the current month.
  - Categories whose total spend changed more than 200% compared to the prior month.
  - Every hit creates a ``Flag`` with ``flag_type="anomaly"``, a clear reason, and
    a severity.
- **`run_reconciliation` command** now calls `run_anomaly_detection(month)` after
  reconciliation and prints an anomaly-detection summary.
- Defensive handling for empty months and Pandas chained-assignment warnings.

**TDD:** extended `core/tests/test_management.py` with 6 anomaly tests first:
no-data exit, vendor z-score anomaly, duplicate within 7 days, new vendor,
category month-over-month jump > 200%, and insufficient history skipping z-score.
Confirmed failures (missing `run_anomaly_detection`, empty-month `KeyError`), then
implemented to green. Full suite: **77 tests pass**.

**Improvements beyond the spec:**
- Separated anomaly rules into a dedicated service module (`core/anomaly/rules.py`)
  so they can be reused outside the management command.
- Used `bulk_create` inside an atomic transaction for efficient flag insertion.
- Lower-cased vendor/category names for case-tolerant grouping and matching.
- Handled the σ = 0 edge case by flagging any current-month amount that differs
  from a constant historical average, rather than silently skipping the vendor.
- Guarded category MoM checks so categories with no prior-month baseline do not
  produce spurious flags.

**Deviations:** None. Live QuickBooks data was not used; all anomaly checks are
exercised against generated `Transaction` records.

---

## Step 9 — `feat(core): step 9 — idempotency for reconciliation, sync, and bank feed`

Made the data pipeline idempotent so repeated runs do not duplicate records.

- **`run_reconciliation`** now deletes existing reconciliation ``Flag`` records
  for the target month (by linked ``Transaction`` or ``BankTransaction`` date)
  before creating the newly computed set, inside the same atomic transaction.
- **`run_anomaly_detection`** now deletes existing anomaly ``Flag`` records whose
  linked ``Transaction`` falls in the target month before inserting the new set,
  also inside an atomic transaction.
- **Category month-over-month anomaly flags** now attach to a representative
  ``Transaction`` for the category so they can be scoped to a month and removed
  on re-run.
- **`sync_quickbooks`** idempotency is already enforced by
  ``Transaction.objects.get_or_create(qb_transaction_id=...)``; added a command-level
  test confirming a second run produces no duplicates.
- **`generate_bank_feed`** already required ``--force`` when bank data exists for
  the month; this behavior is covered by existing tests.

**TDD:** added 3 idempotency tests first:
- `test_reconciliation_is_idempotent` in `RunReconciliationCommandTests`
  (failed: second run doubled reconciliation flags).
- `test_anomaly_detection_is_idempotent` in `AnomalyDetectionCommandTests`
  (failed: second run doubled anomaly flags).
- `test_command_is_idempotent` in `SyncCommandTests`
  (passed because `get_or_create` was already in place, but added for regression
  coverage).

Confirmed failures, implemented month-scoped deletion, then verified all 80 tests
pass (`python manage.py test`).

**Improvements beyond the spec:**
- Scoped deletion uses the related ``Transaction`` / ``BankTransaction`` date so
  flags for other months are never touched.
- Category-level anomaly flags were previously detached from any transaction;
  tying them to a representative transaction keeps deletion precise and gives
  reviewers a clickable starting point.
- Deletion and insertion happen in the same `transaction.atomic()` block, so a
  re-run is all-or-nothing.

**Deviations:** None.

---

## Step 10 — `feat(core): step 10 — agent-drafted close summary via LangGraph/LangChain-Anthropic`

Installed an agent framework and built a close-summary generator.

- **New package `core/agent/`** with `summary.py`:
  - `gather_inputs(month)` collects open ``Flag`` records, monthly category totals,
    prior-month category totals, and total spend.
  - `build_prompt()` renders the inputs into a prompt for the LLM and a deterministic
    fallback.
  - A single-node **LangGraph** graph (`StateGraph`) whose node calls a Claude model
    via **LangChain-Anthropic** when ``ANTHROPIC_API_KEY`` is configured.
  - When no API key is present, the node falls back to a deterministic summary so
    local development and CI do not require live API access.
  - `draft_close_summary(month)` runs the graph and saves/updates a
    ``CloseSummary`` with ``status="draft"`` using ``update_or_create`` (idempotent).
- **New management command `generate_close_summary`** that drafts and prints the
  summary for a given month.
- Added `langchain`, `langchain-anthropic`, and `langgraph` to `requirements.txt`.
- Added `ANTHROPIC_API_KEY` and optional `CLOSE_SUMMARY_MODEL` to `.env.example`.

**TDD:** created `core/tests/test_agent.py` and extended
`core/tests/test_management.py` with 7 tests first: gather_inputs returns category
 totals / open flags only, fallback summary without API key, deterministic fallback
contains inputs, re-running updates existing summary, fake LLM client injection,
and the `generate_close_summary` command creates a draft. Confirmed failures
(`ModuleNotFoundError: core.agent`, `Unknown command: 'generate_close_summary'`),
then implemented to green. Full suite: **87 tests pass**.

**Improvements beyond the spec:**
- The agent module is fully mockable: `draft_close_summary(month, llm=...)` accepts
  a prebuilt LangChain runnable for tests or custom pipelines.
- Close summaries are idempotent via `update_or_create`; running the command twice
  updates the existing draft instead of creating duplicates.
- Category totals exclude blank categories and include prior-month comparisons for
  context.
- Open-flag filtering scopes to the target month and ignores rejected flags.

**Deviations:**
- Live Anthropic summary generation was **not exercised** (no Anthropic API key
  available). The LangGraph/LangChain integration is implemented and the LLM path
  is unit-tested with a fake client; the deterministic fallback is used in the
  standard test suite.

---

## Step 11 — `feat(core): step 11 — demo data seeding command`

Added a single `seed_demo_data` management command that creates a fully populated
month of demo data and runs the entire close pipeline.

- **New module `core/demo_seed.py`** with `seed_demo_data(month, count=20, ...)`:
  - Clears flags and demo ``Transaction`` rows (``qb_transaction_id__startswith="DEMO-"``)
    for the target month before re-seeding.
  - Creates ``count`` synthetic ``Transaction`` records with Faker using realistic
    vendors, categories, GL accounts, and amounts.
  - Runs ``generate_bank_feed`` with ``force=True`` to produce the bank side.
  - Runs ``run_reconciliation`` (which includes anomaly detection) to generate flags.
  - Runs ``draft_close_summary`` to create/update a ``CloseSummary`` draft.
  - Defaults to a deterministic random seed so re-runs produce the same demo data and
    the same flags (idempotent); ``--seed`` lets users vary the data.
- **New management command `seed_demo_data``** with ``month``, optional ``--count``,
  and optional ``--seed`` arguments.
- Added **Faker 40.23.0** to `requirements.txt`.

**TDD:** added 3 tests to `core/tests/test_management.py` first:
- `test_seeds_transactions_bank_feed_flags_and_summary` (failed: unknown command).
- `test_re_running_is_idempotent` (failed: second run produced different flag counts).
- `test_preserves_non_demo_transactions` (failed: unknown command).

Fixed by adding the command, clearing flags before demo transactions, and defaulting
to a deterministic seed. Full suite: **90 tests pass**.

**Improvements beyond the spec:**
- Demo clearing only deletes demo-identified transactions, so any real
  ``Transaction`` rows the user already has are preserved.
- Flags are cleared before transactions to avoid orphaned ``Flag`` records with
  ``NULL`` FKs after the demo rows are deleted.
- The command prints a clear stage summary: transactions created, bank transactions
  created, reconciliation flags created, and close summary month.

**Deviations:** None. Live QuickBooks and Anthropic integrations are still not
exercised; the demo command uses the local fake feed and deterministic summary.

---

## Step 12 — `feat(core): step 12 — Celery + Redis scheduled QuickBooks sync`

Installed Celery and Redis, wired Celery into Django, and added a nightly scheduled
task that runs the QuickBooks sync.

- **New `close_assistant/celery.py`** and updated `close_assistant/__init__.py` to
  load the Celery app alongside Django.
- **`close_assistant/settings.py`** now configures:
  - `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` (defaulting to
    `redis://localhost:6379/0`).
  - `CELERY_TASK_ALWAYS_EAGER` toggle for tests / CI.
  - `CELERY_BEAT_SCHEDULE` with a nightly `sync-quickbooks-nightly` crontab at
    midnight.
- **New `core/tasks.py`** with `sync_quickbooks_task`, a thin `@shared_task` wrapper
  around `call_command("sync_quickbooks")`.
- Added **Celery 5.6.3** and **redis 8.0.0** to `requirements.txt`.
- Added `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, and `CELERY_TASK_ALWAYS_EAGER`
  to `.env.example`.
- Also fixed `core/demo_seed.py` to pass the same deterministic seed into
  `generate_bank_feed`, ensuring `seed_demo_data` re-runs produce identical demo
  data and flags.

**TDD:** created `core/tests/test_celery.py` with 3 tests first: Celery app loads
broker URL from Django settings, beat schedule contains the nightly sync task, and
the task calls `sync_quickbooks`. Confirmed failures (`ModuleNotFoundError` for
`close_assistant.celery` and `core.tasks`), then implemented to green. Full suite:
**93 tests pass**.

**Improvements beyond the spec:**
- The task is a thin wrapper around the existing management command, avoiding
  duplicated sync logic.
- `CELERY_TASK_ALWAYS_EAGER` is configurable from the environment, making it easy to
  run the test suite without a live Redis broker.
- Broker/result-backend URLs are fully environment-driven.

**Deviations:** None. The nightly beat schedule is configured; live Redis and a
running worker are not required for the test suite.

---

## Step 13 — `feat(core): step 13 — HTMX review dashboard`

Built the `/dashboard/` review interface for monthly close review.

- **New dashboard views** in `core/views.py`:
  - `dashboard` — renders the dashboard for a selected month.
  - `flag_approve` / `flag_reject` — POST actions that update a flag's status and
    return the updated table row partial.
  - `summary_review` — POST action that marks a ``CloseSummary`` reviewed and saves
    reviewer notes, returning the updated summary partial.
- **URL routes** added in `core/urls.py`:
  - `/dashboard/`
  - `/dashboard/flag/<id>/approve/` and `/dashboard/flag/<id>/reject/`
  - `/dashboard/summary/<month>/review/`
- **Templates** under `core/templates/core/`:
  - `dashboard.html` — full page extending `base.html`.
  - `dashboard_content.html` — partial swapped by the month selector (`hx-get`).
  - `flag_row.html` — partial row with Approve/Reject buttons (`hx-post`).
  - `close_summary_section.html` — partial summary block with Mark Reviewed form.

**TDD:** created `core/tests/test_dashboard.py` with 5 tests first: dashboard
renders flags and summary, HTMX partial response, flag approve, flag reject, and
close-summary review. Confirmed failures (`NoReverseMatch`), then implemented to
green. Full suite: **98 tests pass**.

**Improvements beyond the spec:**
- The month selector uses HTMX to fetch the partial dashboard content and updates
  the URL via `hx-push-url`.
- Flag actions return only the swapped row, keeping the rest of the page intact.
- The summary section is a separate partial so the review form can update in place.
- Open flags are scoped to the selected month and sorted newest-first.

**Deviations:** None. Access control (login required) is intentionally deferred to
Prompt 14 per the spec.

---

## Step 14 — `feat(core): step 14 — dashboard access control with @login_required`

Required authentication for the review dashboard and all dashboard action views using
Django's built-in auth.

- **`core/views.py`**: added `django.contrib.auth.decorators.login_required` and
  applied it to `dashboard`, `flag_approve`, `flag_reject`, and `summary_review`.
- **`close_assistant/settings.py`**: added `LOGIN_URL = "/accounts/login/"` and
  `LOGIN_REDIRECT_URL = "/dashboard/"`.
- **`close_assistant/urls.py`**: included `django.contrib.auth.urls` at
  `/accounts/` so the built-in login/logout views are available.
- **`core/templates/registration/login.html`**: simple login form extending
  `base.html`.

**TDD:** extended `core/tests/test_dashboard.py` with 4 access-control tests first:
anonymous users are redirected to `/accounts/login/` for the dashboard, flag
approve/reject, and summary review; logged-in users can access the dashboard.
Confirmed failures (302 vs 200/405 for anonymous requests), then implemented to green.
Full suite: **102 tests pass**.

**Improvements beyond the spec:**
- Login redirect points back to the dashboard via `next`, so users land where they
  started after authenticating.
- `login_required` is placed inside `@require_http_methods` / `@require_POST` so
  anonymous POSTs redirect to login instead of returning a 405.

**Deviations:** None. Logout and password-change views come for free via
`django.contrib.auth.urls`, but the dashboard only needs login.

