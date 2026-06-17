# Agent Instructions
## Workflow: Test-Driven Development
1. Write failing tests first
2. Confirm they fail for the right reasons
3. Write minimum code to make them pass
4. Refactor if needed, keeping tests green

---
 
## For Every task
 
### docs/CURRENT_TASK.md
Keep this file up to date at all times. It should always reflect exactly what is happening right now and should be updated
before working on the step:
- The current step number and name
- What you are actively working on
- Any blockers or decisions being made
- What the next step will be

Overwrite it completely each time you move to a new step. It should never describe a completed step — only the live current state.

### docs/CHANGELOG.md
Append an entry after every commit. Each entry should include:
- The step number and commit message
- A plain-English summary of what was built
- Any refactors or improvements made beyond the spec (see below)
- Any deviations from the spec and why

**Move anything from the next section that is not completed to `docs/TODO.md`** 

---
 
**Output a commit message:**
```
<type>(<scope>): <summary>
- <what changed>
```
Types: `feat` `fix` `test` `refactor` `chore` `docs`
 
---

## Rules
- Never write implementation before tests
- Django: split tests into `test_models.py`, `test_views.py`, `test_serializers.py`
- No commit message if tests are failing
- Never commit secrets, keys, or credentials — use .env
## Docker Test Context
- Backend `DATABASE_URL` uses Docker hostname `db`, so Django tests must run inside the backend container.
- Use: `docker compose exec backend python manage.py test ...`
- Avoid host-shell `python backend/manage.py test ...` unless DB host is explicitly configured for host access.
