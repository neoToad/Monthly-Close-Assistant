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

**Deviations:**
- **Live sandbox pull NOT exercised** (no sandbox credentials available). The OAuth
  flow and sync pipeline are fully implemented and unit-tested against mocked
  QuickBooks responses; the live pull against the Intuit sandbox is deferred and
  noted in `docs/TODO.md`. Per the foundation prompt's instruction, this is recorded
  here explicitly.
- Retry/backoff on QuickBooks API errors is deferred to Prompt 5.