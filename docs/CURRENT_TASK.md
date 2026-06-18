# CURRENT_TASK

## Stage

Build (Prompts 4–18) — IN PROGRESS. Prompt 14 complete; starting Prompt 15.

## Current task

Step 15 — Dockerize. Wrap the Django app, Postgres, and Redis in Docker Compose for
local development and consistent CI. Add a `Dockerfile`, `docker-compose.yml`, and any
supporting entrypoint scripts. Keep the test suite green inside the container context.

## Completion criteria

- `Dockerfile` builds a production-ready Django image.
- `docker-compose.yml` brings up:
  - web app container (depends on db/redis)
  - Postgres container (persistent volume)
  - Redis container (for Celery broker/result backend)
- App container runs migrations, collectstatic, and a development server (or gunicorn).
- `python manage.py test` passes inside the container or against the composed stack.
- `.env.example` updated with any new variables (e.g., `REDIS_URL`).
- `docs/CURRENT_TASK.md` overwritten for Prompt 16, `docs/CHANGELOG.md` appended,
  `docs/TODO.md` updated, and changes committed with the Prompt 15 commit message.

## Branch

`feature/close-assistant-build`
