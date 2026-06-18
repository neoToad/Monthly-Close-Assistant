# Deployment Guide — Railway (Prompt 17)

This document describes how to deploy the Monthly Close Assistant to [Railway](https://railway.app).
It is a reference checklist; the live deployment was **not exercised** in this build because no Railway account credentials or project tokens were available.

## What Railway needs

Railway can deploy the app directly from the included `Dockerfile` because the repository already ships a containerized Django stack.

### 1. Create the project

- Push the `feature/close-assistant-build` branch to GitHub (already done during the build).
- In Railway, choose **New Project → Deploy from GitHub repo** and select this repo.
- Railway detects `Dockerfile` and builds the `web` service automatically.

### 2. Add data services

Add two managed services from the Railway dashboard:

- **PostgreSQL** — Railway exposes a `DATABASE_URL` environment variable automatically.
  The `close_assistant/settings.py` module reads `DATABASE_URL` via `dj-database-url` and
  ignores the individual `DB_*` variables when it is present.
- **Redis** — add a Redis service and copy its public URL into `CELERY_BROKER_URL` and
  `CELERY_RESULT_BACKEND`.

### 3. Required environment variables

Set these in the Railway service variables panel:

| Variable | Value / source | Notes |
| --- | --- | --- |
| `SECRET_KEY` | Generate a strong random key | Required for sessions/signing. |
| `DATABASE_URL` | Provided by Railway Postgres | Used automatically by `dj-database-url`. |
| `CELERY_BROKER_URL` | Provided by Railway Redis | e.g. `redis://...` |
| `CELERY_RESULT_BACKEND` | Provided by Railway Redis | Same as broker URL. |
| `ALLOWED_HOSTS` | Railway app domain + custom domain | Comma-separated, no spaces. |
| `DEBUG` | `False` | Never run production with `DEBUG=True`. |
| `QB_ENVIRONMENT` | `sandbox` or `production` | Matches the linked QuickBooks app. |
| `QB_CLIENT_ID` | From Intuit developer dashboard | OAuth 2.0 client ID. |
| `QB_CLIENT_SECRET` | From Intuit developer dashboard | OAuth 2.0 secret. |
| `QB_REDIRECT_URI` | `https://<your-domain>/quickbooks/oauth/callback/` | Must be registered in Intuit. |
| `QB_SANDBOX_COMPANY_ID` | QuickBooks realm id | For sandbox pulls. |
| `QB_TOKEN_ENCRYPTION_KEY` | Fernet key generated locally | Encrypts tokens at rest. |
| `ANTHROPIC_API_KEY` | From Anthropic console | Optional; omit to use deterministic summaries. |
| `CLOSE_SUMMARY_MODEL` | e.g. `claude-sonnet-4-6` | Optional model override. |

### 4. Start the web service

Railway builds and starts the `web` container using the `Dockerfile` `CMD`, which runs
Gunicorn. The entrypoint runs migrations and `collectstatic` on every deploy.

### 5. Celery worker and beat

To run background tasks and the nightly QuickBooks sync, create two additional
services that use the same image and environment:

- **Worker**: `celery -A close_assistant worker -l info`
- **Beat**: `celery -A close_assistant beat -l info`

Both must share the same Redis broker/result backend as the web app.

### 6. Post-deploy verification

- Visit `/admin/` to confirm Django loads.
- Run `/quickbooks/oauth/start/` to verify the QuickBooks OAuth redirect.
- Run `seed_demo_data 2025-01` from a Railway shell to populate demo data and confirm
the reconciliation / anomaly / summary pipeline works end-to-end.

## Status

Live Railway deployment was **not exercised** in this build (no credentials available).
The Dockerfile, compose stack, and environment-driven settings are ready for Railway's
container-based deploy.
