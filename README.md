# Monthly Close Assistant

An internal Django tool that pulls QuickBooks transactions, simulates a matching bank
feed, reconciles the two sides, flags anomalies, drafts a monthly close summary with
an LLM, and presents everything in a lightweight HTMX dashboard for human review.

## Features

- **QuickBooks sync** — OAuth 2.0 connection to QuickBooks Online, pulls
  Purchase / Deposit / JournalEntry records, and stores them as normalized
  `Transaction` rows.
- **Testing bank feed** — optionally generates a configurable bank-side transaction
  set with realistic discrepancies for validating reconciliation logic.
- **Reconciliation engine** — Pandas-based matching on vendor, amount within $0.01,
  and date within 1 day; creates `Flag` records for mismatches and unmatched rows.
- **Anomaly detection** — rule-based checks for vendor amount z-scores, duplicate
  transactions within 7 days, new vendors, and category month-over-month jumps > 200%.
- **Close-summary agent** — LangGraph/LangChain-Anthropic agent that drafts a
  month-end summary; falls back to deterministic output when no API key is set.
- **HTMX review dashboard** — month selector, open flags table, approve/reject
  actions, and close-summary review, all server-rendered with HTMX partial updates.
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

The latest full-suite result: **114 tests pass**.

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
| `python manage.py sync_quickbooks` | Pulls Purchase/Deposit/JournalEntry records from QuickBooks and stores normalized `Transaction` rows. Idempotent keyed on `qb_transaction_id`. |
| `python manage.py generate_bank_feed YYYY-MM` | *(Testing only)* Generates a synthetic bank side for a month with configurable discrepancy rates. Use `--force` to overwrite. |
| `python manage.py run_reconciliation YYYY-MM` | Reconciles GL and bank rows for the month and runs anomaly detection. Idempotent. |
| `python manage.py generate_close_summary YYYY-MM` | Drafts a close summary for the month (LLM if `ANTHROPIC_API_KEY` is set, deterministic fallback otherwise). |

To pull real QuickBooks data, connect your app via `/quickbooks/oauth/start/` and then
sync from the dashboard or run `python manage.py sync_quickbooks`.

## Dashboard

The review dashboard lives at `/dashboard/` and requires authentication. It shows:

- A month selector that HTMX-swaps the dashboard content.
- All open flags for the selected month with Approve / Reject actions.
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

`.github/workflows/ci.yml` runs on every push and pull request to `main` and
`feature/close-assistant-build`. It builds the Docker compose stack and runs the full
Django test suite inside the `web` container.

## License

Internal project — not licensed for public distribution.
