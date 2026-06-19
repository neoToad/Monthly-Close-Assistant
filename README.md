# Monthly Close Assistant

An internal Django tool that pulls QuickBooks transactions, simulates a matching bank
feed, reconciles the two sides, flags anomalies, drafts a monthly close summary with
an LLM, and presents everything in a lightweight HTMX dashboard for human review.

## Features

- **QuickBooks sync** — OAuth 2.0 connection to QuickBooks Online, pulls
  Purchase / Deposit / JournalEntry / Bill / BillPayment / VendorCredit records,
  stores them as normalized `Transaction` rows, and syncs the chart of accounts
  into `QBAccount`. Supports multiple connected companies (realms).
- **Testing bank feed** — optionally generates a configurable bank-side transaction
  set with realistic discrepancies for validating reconciliation logic. A
  `--cash-only` mode restricts the feed to cash-movement sources (Purchase,
  Deposit, BillPayment, and cash-like JournalEntry lines).
- **Reconciliation engine** — Pandas-based matching on vendor, amount within $0.01,
  and date within 1 day; creates `Flag` records for mismatches and unmatched rows.
  Also performs account-level balance reconciliation by comparing stored bank
  statement balances to posted GL totals for each cash account.
- **AI-assisted account reconciliation** — for each unreconciled cash account, the
  assistant proposes explainable adjusting entries (Purchase / Deposit / JournalEntry)
  that close the bank-to-GL gap. Suggestions default to a deterministic fallback, with
  optional LLM enhancement via Anthropic or OpenAI when API keys are configured.
  A reviewer previews each proposal in a modal, confirms, and the app writes real
  QuickBooks objects, re-syncs, and refreshes the dashboard.
- **Anomaly detection** — rule-based checks for vendor amount z-scores, duplicate
  transactions within 7 days, new vendors, and category month-over-month jumps > 200%.
- **Close-summary agent** — LangGraph/LangChain-Anthropic agent that drafts a
  month-end summary, optionally cross-checking totals against the QuickBooks
  GeneralLedger report; falls back to deterministic output when no API key is set.
- **HTMX review dashboard** — company and month selectors, open flags table,
  approve/reject actions, close-summary review, and a "Bank Balances" panel with
  inline statement-balance entry, all server-rendered with HTMX partial updates.
- **Scheduled tasks** — Celery + Redis beat schedule runs the nightly QuickBooks sync.
- **Dockerized** — `docker compose` stack with Postgres, Redis, web app, Celery worker,
  and beat scheduler.
- **CI/CD** — GitHub Actions builds the Docker images and runs the full test suite in
  the container on every push and pull request.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  QuickBooks │────▶│   Django     │────▶│   Postgres      │
│   Online    │     │   close_assistant   │     │   (Transactions,  │
│   API       │     │              │     │    Flags, etc.) │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
  ┌───────────┐     ┌────────────┐     ┌────────────┐
  │  Fake     │     │Reconciliation│     │  Anomaly   │
  │ bank feed │     │   engine   │     │   rules    │
  └───────────┘     └────────────┘     └────────────┘
                           │                  │
                           └────────┬─────────┘
                                    ▼
                           ┌─────────────────┐
                           │  HTMX dashboard │
                           │  (approve/reject)│
                           └─────────────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │ Close-summary   │
                           │ agent (LLM)     │
                           └─────────────────┘
```

The main application lives in the `core` Django app. QuickBooks integration is split
into `core/quickbooks/` (OAuth, token encryption, normalization, sync), reconciliation
into `core/reconciliation/`, anomaly detection into `core/anomaly/`, and the summary
agent into `core/agent/`.

## Local setup

### With Docker Compose (recommended)

1. Clone the repo and switch to the build branch:

   ```bash
   git clone https://github.com/neoToad/Monthly-Close-Assistant.git
   cd Monthly-Close-Assistant
   git checkout feature/close-assistant-build
   ```

2. Copy `.env.example` to `.env` and fill in real QuickBooks values:

   ```bash
   cp .env.example .env
   ```

3. Build and start the stack:

   ```bash
   docker compose up --build
   ```

4. Open the dashboard at http://localhost:8000/dashboard/.

### Without Docker

You need Python 3.13+ and a running Postgres server. This machine has local Postgres 17
and 18 on ports `5432` and `5433`; the dev config uses a Docker Postgres container on
port `5434`:

```bash
docker run -d --name close_pg \
  -e POSTGRES_DB=close_assistant \
  -e POSTGRES_USER=close_app \
  -e POSTGRES_PASSWORD=close_dev_pw \
  -p 5434:5432 postgres:17
```

Then:

```bash
python -m venv ../.venvs/MonthlyCloseAssistant
../.venvs/MonthlyCloseAssistant/Scripts/activate  # Windows
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

## Running tests

The test suite is written with Django's `TestCase`/`SimpleTestCase` and runs against
Postgres (not SQLite).

Inside Docker:

```bash
docker compose run --rm web python manage.py test --noinput
```

On the host (when `DB_HOST` points at the dev Postgres):

```bash
python manage.py test --noinput
```

The latest full-suite result: **265 tests pass**.

## Required environment variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django signing/encryption key. Generate a strong value for production. |
| `DATABASE_URL` | Postgres URL (e.g. `postgres://close_app:close_dev_pw@db:5432/close_assistant`). Takes precedence over `DB_*` vars. |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | Postgres connection used when `DATABASE_URL` is not set. |
| `CELERY_BROKER_URL` | Redis URL for Celery (e.g. `redis://redis:6379/0`). |
| `CELERY_RESULT_BACKEND` | Redis URL for Celery results. |
| `CELERY_TASK_ALWAYS_EAGER` | Set `True` to run tasks synchronously (useful for tests). |
| `QB_CLIENT_ID` | QuickBooks OAuth client ID. |
| `QB_CLIENT_SECRET` | QuickBooks OAuth client secret. |
| `QB_REDIRECT_URI` | Must match a URI registered in the Intuit dashboard. |
| `QB_ENVIRONMENT` | `sandbox` or `production`. |
| `QB_TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting tokens at rest. |
| `QB_TOKEN_REFRESH_BUFFER_MINUTES` | Minutes before expiry to refresh proactively. |
| `CLOSE_SUMMARY_PROVIDER` | `anthropic` (default) or `openai` for OpenAI-compatible APIs. |
| `ANTHROPIC_API_KEY` | Optional; enables Claude-drafted close summaries. |
| `OPENAI_API_KEY` | Optional; used when `CLOSE_SUMMARY_PROVIDER=openai` (e.g. Ollama Cloud). |
| `OPENAI_BASE_URL` | Optional; base URL for an OpenAI-compatible API. |
| `CLOSE_SUMMARY_MODEL` | Optional model override (e.g. `qwen3.5:cloud`). |

See `.env.example` for the full list and comments.

## Management commands

| Command | What it does |
| --- | --- |
| `python manage.py sync_quickbooks` | Pulls records for all connected QuickBooks realms, or use `--realm-id` to sync one. Now includes `Bill`, `BillPayment`, `VendorCredit`, and the chart of accounts (`QBAccount`). Idempotent keyed on `(company, qb_transaction_id)` and `(company, account_id)`. Use `--skip-accounts` to skip chart sync. |
| `python manage.py generate_bank_feed YYYY-MM` | *(Testing only)* Generates a synthetic bank side for a month. Use `--realm-id` to scope to one realm, `--force` to overwrite, and `--cash-only` to restrict to cash-movement sources. |
| `python manage.py run_reconciliation YYYY-MM` | Reconciles GL and bank rows for the month; use `--realm-id` to scope to one realm. Runs anomaly detection and account-level balance checks. Idempotent. |
| `python manage.py generate_close_summary YYYY-MM` | Drafts a close summary for the month; use `--realm-id` to scope to one realm. Cross-checks against the QuickBooks GeneralLedger report when a client is available. |
| `python manage.py set_bank_balance YYYY-MM --realm-id <id> --account-id <id> --balance <amount>` | Manually set the ending bank balance for a cash account and month. Used by the balance-reconciliation check. |
| `python manage.py seed_bank_balances YYYY-MM --realm-id <id>` | *(Sandbox convenience)* Pull current account balances from QuickBooks and seed `BankStatementBalance` rows for cash-like accounts. Use `--force` to overwrite. |
| `python manage.py suggest_account_fixes YYYY-MM --account-id <id> --realm-id <id>` | Generate adjusting-entry suggestions for a single cash account. Prints a dry-run list; add `--apply` to execute the highest-confidence tier in QuickBooks. |
| `python manage.py apply_account_fix YYYY-MM --account-id <id> --suggestion-id <id> --realm-id <id>` | Preview a single suggestion; add `--apply` to write it to QuickBooks. |

To pull real QuickBooks data, connect your app via `/quickbooks/oauth/start/` and then
sync from the dashboard or run `python manage.py sync_quickbooks`.

## Dashboard

The review dashboard lives at `/dashboard/` and requires authentication. It shows:

- A **company selector** that filters every view by the connected QuickBooks realm.
  Company names are fetched automatically from QuickBooks; the selector falls back to
  the raw `realm_id` when a name is unavailable.
- A month selector that HTMX-swaps the dashboard content.
- A **Bank Balances** panel listing each cash account's stored statement balance and
  posted GL total, highlighting any unreconciled gaps. Use the inline form to set a
  balance manually, or click **Reconcile** to open the AI-assisted reconciliation
  modal, preview proposed adjusting entries, and confirm writes to QuickBooks.
- All open flags for the selected company and month with Approve / Reject actions.
  Balance-reconciliation flags are styled with a "Balance" badge.
- The current close summary and a form to mark it reviewed with notes.

Create a user for local testing:

```bash
docker compose run --rm web python manage.py createsuperuser
```

## Deployment

The app is packaged as a Docker image and documented for Railway in `docs/DEPLOY.md`.
Railway can deploy directly from the `Dockerfile`; add managed Postgres and Redis
services, set the environment variables, and (optionally) run separate worker and beat
services for Celery.

A live Railway deployment was **not exercised** during this build because no Railway
credentials were available.

## CI/CD

The GitHub Actions workflow was removed from this branch. Run the test suite locally
inside the Docker `web` container:

```bash
docker compose exec web python manage.py test --noinput
```

## License

Internal project — not licensed for public distribution.
