# Monthly Close Assistant — CLI Agent Build Prompts (Full Sequence)

Copy/paste prompts for a CLI coding agent (Claude Code, Cursor CLI, Aider, etc.) to
scaffold and build this project step by step. Run them in order, in the project's
root directory. Review the agent's output at each step before moving to the next.

Testing is intentionally not a separate step here since TDD is already covered in
agents.md, write tests as part of each step per that workflow.

---

## 1. Project Scaffolding

```
Create a new Django project called close_assistant with a core app inside it.
Configure PostgreSQL as the database using environment variables (DB_NAME, DB_USER,
DB_PASSWORD, DB_HOST, DB_PORT) loaded via python-decouple. Install and configure
django-htmx, and wire HTMX into a base.html template. Set up a .env.example file
listing all required environment variables. Do not commit a real .env file.
```

---

## 2. Postgres Schema

```
In the core app, create Django models for:
- Transaction: represents a QuickBooks-sourced transaction (date, vendor, amount,
  category, gl_account, qb_transaction_id, source_type)
- BankTransaction: same shape as Transaction but represents the bank-feed side,
  with a nullable matched_transaction_id foreign key to Transaction
- Flag: represents a reconciliation or anomaly issue (flag_type, related transaction
  or bank_transaction, reason, severity, status [open/approved/rejected], created_at)
- CloseSummary: represents an agent-generated monthly close draft (month, summary_text,
  status [draft/reviewed], reviewer_notes, created_at)

Write and apply the migrations. Register all models in Django admin.
```

---

## 3. QuickBooks OAuth + Data Pull

```
Install python-quickbooks and intuit-oauth. Implement QuickBooks OAuth 2.0 in this
Django project: a view to start the OAuth flow, a callback view to receive and store
the access/refresh tokens securely, and a token refresh helper. Read the client ID,
client secret, and redirect URI from environment variables.

Then write a Django management command called sync_quickbooks that authenticates
using the stored tokens and pulls Purchase, Deposit, and JournalEntry records from
the QuickBooks sandbox company, normalizing each into the Transaction model. Skip
records that already exist (match on qb_transaction_id).
```

---

## 4. QuickBooks Secrets & Environment Config

```
Review the .env.example file and OAuth implementation. Make sure it explicitly
lists and documents: QB_CLIENT_ID, QB_CLIENT_SECRET, QB_REDIRECT_URI,
QB_SANDBOX_COMPANY_ID, QB_ENVIRONMENT (sandbox or production), and
QB_TOKEN_REFRESH_BUFFER_MINUTES (how early to refresh before expiry). Add a comment
above each variable in .env.example explaining what it's for and where to get the
value from the QuickBooks developer dashboard. Make sure the OAuth code reads
QB_ENVIRONMENT and points at the correct QuickBooks API base URL accordingly.
```

---

## 5. Error Handling & Edge Cases (QuickBooks Sync)

```
Review the QuickBooks sync code written so far and add explicit error handling for:
- QuickBooks access token expired mid-sync: catch the auth error, refresh the
  token, and retry the request once before failing loudly with a clear log message
- QuickBooks API rate limiting or timeout: retry with exponential backoff up to
  3 attempts, then fail with a clear error message instead of crashing silently

All of these should produce clear log output (not just silent failures) so issues
are debuggable from logs alone.
```

---

## 6. Fake Bank Feed Generator

```
Write a Django management command called generate_bank_feed that reads all
Transaction records for a given month (pass month as an argument) and generates
corresponding BankTransaction records, deliberately introducing realistic
discrepancies using these configurable rates:
- drop_rate (default 0.05): some transactions are skipped entirely, not copied
- dup_rate (default 0.03): some transactions are duplicated
- amount_shift_rate (default 0.04): some amounts are nudged by a small random
  delta (e.g. -2.50 to 3.75) to simulate fees or rounding
- date_shift_rate (default 0.05): some dates are shifted by 1-2 days to simulate
  posting delays
- extra_rate (default 0.03): add a few bank-only transactions with no matching
  Transaction record at all

Use Pandas for the data manipulation. Print a summary at the end showing how many
of each discrepancy type were introduced, so the ground truth is documented for
testing the reconciliation logic against.
```

---

## 7. Reconciliation Logic

```
Write a reconciliation module using Pandas that compares Transaction and
BankTransaction records for a given month. Match records on vendor, amount, and
date within a tolerance (amount within $0.01, date within 1 day). For every
unmatched or mismatched pair, create a Flag record with flag_type="reconciliation"
and a clear, human-readable reason (e.g. "Bank shows $452.00 but GL shows $450.00",
or "Transaction exists in GL but not in bank feed"). Wire this into a management
command called run_reconciliation that takes a month argument.
```

---

## 8. Anomaly Detection

```
Add anomaly detection rules to the reconciliation module (or a separate
anomaly_detection module), using Pandas/NumPy. For a given month's Transaction
data, flag:
- Any transaction more than 2 standard deviations from that vendor's historical
  average amount (using prior months' data); skip this check for vendors with only
  one or two historical data points rather than dividing by zero or a near-zero
  sample size, and log that it was skipped and why
- Duplicate transactions: same vendor, same amount, within the same 7-day window
- New vendors with no transaction history before this month
- Categories where total spend changed more than 200% compared to the prior month

A month with zero transactions should exit cleanly with a "no data for this month"
message, not throw an exception.

Create Flag records with flag_type="anomaly" and a clear reason for each. Wire this
into the run_reconciliation command so it runs both reconciliation and anomaly
checks together.
```

---

## 9. Idempotency for Reconciliation & Sync

```
Update run_reconciliation so that re-running it for a month that's already been
processed does not create duplicate Flag records. Before creating a new Flag,
check whether an open or resolved Flag already exists for that exact transaction
and flag_type, and skip if so. Apply the same idempotency check to sync_quickbooks
using the existing qb_transaction_id match, and to generate_bank_feed, if a
BankTransaction set already exists for that month, prompt before regenerating
(or accept a --force flag to overwrite).
```

---

## 10. Agent Layer

```
Install crewai (or langgraph and langchain-anthropic, your choice based on what's
already set up). Build an agent step that takes all open Flag records for a given
month, plus that month's Transaction totals by category and the prior month's
totals for comparison, and generates a plain-language close summary covering:
what changed this month, what was flagged and why, and what needs human review.

The agent must only produce draft text. It must not modify any Flag, Transaction,
or BankTransaction records. Save its output as a CloseSummary record with
status="draft". Wire this into a management command called generate_close_summary
that takes a month argument.
```

---

## 11. Demo Data Seeding

```
Create a single management command called seed_demo_data that sets up everything
needed to demo this project end to end without depending on a live QuickBooks API
call. It should:
- Check if Transaction records already exist for a demo month; if not, generate a
  realistic set using Faker (vendors, categories, amounts, dates) instead of
  calling QuickBooks
- Run generate_bank_feed against that demo data to create the corrupted
  BankTransaction records
- Run reconciliation and anomaly detection to populate Flag records
- Run the agent summary generation to create a CloseSummary draft
- Print a summary at the end: how many transactions, flags, and the summary
  status, so it's obvious the seed worked

This command should be safe to run repeatedly without creating duplicate data,
check for existing demo records first and skip or clear them as appropriate.
```

---

## 12. Celery Scheduled Sync

```
Install celery and redis. Configure Celery with this Django project using Redis
as the broker. Create a scheduled task that runs sync_quickbooks nightly. Add the
Celery worker and beat configuration needed to run this locally and in Docker.
```

---

## 13. HTMX Review Dashboard

```
Build a Django view and template for a review dashboard at /dashboard/. It should
show:
1. A month selector dropdown that reloads the page content via hx-get without a
   full page refresh
2. A table of open Flag records for the selected month, each row with Approve and
   Reject buttons using hx-post that update the flag's status and swap in the
   updated row via a partial template, no full reload
3. A section below showing the CloseSummary draft text for that month, with a
   "Mark Reviewed" button using hx-post that updates its status and lets the
   reviewer add notes in a text field before submitting

Style it cleanly but simply, this is an internal tool, not a polished product.
```

---

## 14. Dashboard Access Control

```
Add authentication to the /dashboard/ view and all flag approve/reject endpoints
using Django's built-in auth system. Require login for every dashboard-related
view with @login_required. Create a simple createsuperuser-based admin user setup
documented in the README. Do not allow any flag status changes or close summary
review actions from an unauthenticated request.
```

---

## 15. Dockerize

```
Write a Dockerfile for this Django project and a docker-compose.yml that includes
services for the Django app, PostgreSQL, Redis, and a Celery worker. Use
environment variables for all secrets and connection strings, referencing the
existing .env.example file. Make sure migrations run automatically on container
startup.
```

---

## 16. CI/CD

```
Write a GitHub Actions workflow file that runs on push to main: installs
dependencies, runs the project's test suite, and if tests pass, triggers a deploy
to Railway. Use GitHub secrets for any credentials needed in the workflow.
```

---

## 17. Deploy

```
Deploy this Dockerized Django project to Railway. Set up the PostgreSQL and Redis
add-ons, configure environment variables for QuickBooks OAuth and the database
connection, and verify the deployed app can reach the QuickBooks sandbox.
```

---

## 18. README

```
Write a README.md for this project covering: what the project does and why
(reconciliation + anomaly detection + AI-drafted close summary, human-in-the-loop
review), the architecture (a short diagram or bullet list of the data flow from
QuickBooks through to the dashboard), setup instructions (env vars needed, how to
run migrations, how to run seed_demo_data for a quick local demo without
QuickBooks access), how to run the full pipeline manually (sync, generate bank
feed, reconciliation, agent summary, in order), and how to run it with Docker.
Keep it clear enough that someone unfamiliar with the project could clone it and
get a working demo running in under 10 minutes using the demo seed command.
```

---

## Stretch / Nice-to-Have Prompts

Run any of these after step 18, once the core project is functionally complete.

**Category trend chart:**
```
Add a Chart.js chart (loaded via CDN, no React) to the dashboard showing total
spend by category for the last 6 months, fed by a Django view that aggregates
Transaction data.
```

**Memory across months:**
```
Update the anomaly detection logic to compare each month against a rolling
average of the prior 3-6 months instead of just the immediately preceding month.
Make sure this works correctly even in the first few months when less history
exists.
```

**Audit log:**
```
Add an AuditLog model that records every Flag's lifecycle: when it was created,
and when/how it was resolved (approved/rejected, by whom, with what notes, and
when). Update the dashboard's approve/reject actions to write to this log
automatically.
```

**PDF export:**
```
Install WeasyPrint and add a view that renders an approved CloseSummary as a
downloadable PDF, including the summary text and a table of the flags it
references.
```
