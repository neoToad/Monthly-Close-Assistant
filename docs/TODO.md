# TODO

Items deferred to later stages (per the prompt sequence). Moved here from the running
plan so the current step stays uncluttered.

## Current — Prompt 10
- Agent layer / close-summary generation.
- `generate_close_summary` management command.

## Upcoming
- Prompt 11 — Demo data seeding (`seed_demo_data`).
- Prompt 12 — Celery scheduled sync.
- Prompt 13 — HTMX review dashboard.
- Prompt 14 — Dashboard access control.
- Prompt 15 — Dockerize.
- Prompt 16 — CI/CD.
- Prompt 17 — Deploy to Railway (or document as not exercised if no credentials).
- Prompt 18 — README.

## Open questions / future layout
- Django project currently lives at repo root (per the Foundation prompt). If a later
  Docker stage expects a `backend/` subdirectory layout (per AGENTS.md Docker test
  context), reconcile then — either set the container WORKDIR to the repo root or
  reorganize the project into `backend/`.

## Live QuickBooks sandbox pull
- Not exercised against a live sandbox in Prompt 3 (no sandbox credentials available).
  OAuth flow and `sync_quickbooks` are unit-tested against mocked QuickBooks responses.
  Revisit once sandbox credentials are supplied.
