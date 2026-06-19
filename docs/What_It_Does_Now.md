# What the Monthly Close Assistant Does Right Now

This doc is meant for a human reader and for any future LLM collaborator. It explains what the system currently does, what problems it is trying to solve, where it succeeds, and where it is unclear or incomplete. It is intentionally critical and asks questions that the code alone cannot answer.

---

## 1. The big picture

The Monthly Close Assistant is a Django-based internal tool that helps a bookkeeper, controller, or CFO review a month's financial activity before "closing the books." It connects to one or more QuickBooks Online companies (realms), pulls the recorded GL transactions, optionally compares them to a generated or imported bank-side feed, flags items that look wrong or unmatched, drafts a plain-language close summary, and presents everything in a lightweight HTMX dashboard for human approval.

The project is built as a portfolio / interview demonstration for an AI-agent-builder role. That context matters: it deliberately mixes rule-based financial checks, LLM-generated narrative, and a human-in-the-loop review step.

---

## 2. What it currently does

### 2.1 Pulls data from QuickBooks Online

- Uses OAuth 2.0 (authorization-code flow) to connect to QuickBooks Online.
- Stores encrypted access/refresh tokens in a `QBToken` model.
- Pulls `Purchase`, `Deposit`, and `JournalEntry` records and normalizes them into a single internal `Transaction` table.
- Supports **multiple connected companies** by scoping every synced transaction with a `realm_id`. Each company gets a `QuickBooksCompany` record.
- Refreshes tokens proactively and retries transient QuickBooks errors with exponential backoff.
- Runs the nightly sync on a Celery + Redis schedule.

### 2.2 Generates a synthetic bank feed for testing

- `generate_bank_feed(month, ...)` reads the GL `Transaction` rows for a month and creates matching `BankTransaction` rows.
- Introduces configurable discrepancies:
  - `drop_rate` — bank rows that are missing.
  - `dup_rate` — bank rows that appear twice.
  - `amount_shift_rate` — amounts shifted by small deltas.
  - `date_shift_rate` — dates shifted by 1–2 days.
  - `extra_rate` — bank-only rows with no GL match.
- The generator is explicitly labeled as a **testing tool**, not a production data source.

### 2.3 Reconciles GL against bank feed

- Loads both sides into Pandas DataFrames for a given month and realm.
- Matches rows on lower-cased vendor equality, amount within $0.01, and date within 1 day.
- Creates `Flag` records for:
  - amount mismatches,
  - date mismatches beyond tolerance,
  - bank-only rows,
  - GL-only rows.
- Deletes prior reconciliation flags for that month+realm before inserting the new set, so re-running is idempotent.

### 2.4 Detects anomalies

Rule-based checks on `Transaction` rows for the month:

- Vendor z-score: amounts more than 2 standard deviations from that vendor's historical average.
- Duplicate transactions: same vendor + amount within a 7-day window.
- New vendors: vendors with no transaction history before the current month.
- Category month-over-month jump: category totals that changed more than 200% compared to the prior month.

Like reconciliation, anomaly detection deletes and re-creates anomaly flags for the target month+realm on each run, so it is idempotent.

### 2.5 Drafts a close summary with an LLM agent

- `gather_inputs(month, realm_id)` collects open flags, category totals for the month, prior-month category totals, and total spend.
- Builds a prompt and feeds it to a LangGraph graph.
- Supports two providers:
  - Anthropic/Claude via `langchain-anthropic`.
  - OpenAI-compatible APIs (e.g. Ollama Cloud) via `langchain-openai`, configured with `CLOSE_SUMMARY_PROVIDER`, `OPENAI_API_KEY`, and `OPENAI_BASE_URL`.
- Falls back to a deterministic plain-text summary when no API key is configured, so local dev and CI do not require live LLM access.
- Saves the summary to `CloseSummary` with `status="draft"`, keyed by `(realm_id, month)`, so re-running updates rather than duplicates.

### 2.6 Presents an HTMX review dashboard

- URL: `/dashboard/`
- Authenticated users only (`@login_required`).
- Company selector + month selector.
- Lists open flags for the selected month and company.
- Each flag row shows vendor, reason, amount, a status dot, and **Approve / Reject** buttons.
- Approve/Reject are HTMX `POST`s that update only the flag row partial in place.
- A draft close summary section with a "Mark Reviewed" form that records reviewer notes.
- Dashboard actions for sync, reconcile, and draft-summary generation.

### 2.7 Deployable as Docker + GitHub Actions

- `docker compose` stack: Postgres 17, Redis 7, web (Gunicorn), Celery worker, Celery beat.
- GitHub Actions CI builds the stack and runs the Django test suite on every push/PR to `main` or `feature/close-assistant-build`.
- `docs/DEPLOY.md` describes a Railway deployment path, though it has not been exercised.

---

## 3. What problems it is trying to solve

1. **Month-end close is tedious and error-prone.** Comparing bank records to QuickBooks by hand, spotting weird transactions, and writing a summary takes time. The tool automates the mechanical parts.
2. **Anomalies hide in routine data.** Small amount differences, duplicate charges, new vendors, and category spikes are easy to miss. The rule-based engine surfaces them explicitly.
3. **LLMs can narrate but should not decide.** The agent drafts summaries for human review; it never posts journal entries or approves flags.
4. **Multiple QuickBooks companies need independent review.** The `realm_id` scoping keeps companies isolated while using the same database and dashboard.
5. **Testing reconciliation against real bank data is hard.** The synthetic bank feed provides known, reproducible discrepancies so the reconciliation logic can be validated.

---

## 4. Where it currently succeeds

- **Test coverage is high and real:** 148+ tests, run inside Docker against Postgres, covering models, QuickBooks sync, reconciliation, anomaly detection, agent summary, dashboard, Docker config, CI/CD, and design-system constraints.
- **Idempotency is built in:** repeated syncs, reconciliation runs, anomaly runs, bank-feed generation, and summary drafting do not duplicate data.
- **Multi-company scoping is complete:** schema, constraints, dashboard selector, management commands, and test coverage all treat `realm_id` as a first-class axis.
- **Human-in-the-loop is explicit:** flags stay "open" until a person approves or rejects them; the agent only drafts.
- **Fallbacks keep it runnable without live credentials:** deterministic summary fallback, plaintext token encryption fallback, synthetic bank feed.
- **Design system is intentional:** a flat, ledger-like UI with WCAG AA contrast, responsive layout, and no card/pill chrome.

---

## 5. Critical questions and known gaps

These are not necessarily bugs, but they are places where the current implementation leaves important product or engineering questions unanswered.

### 5.1 The synthetic bank feed is still the only "bank" source

- **Question:** Is there a real bank-feed integration planned (Plaid, Yodlee, CSV upload, OFX/QFX import)? The current generator is good for tests but does not model how the production system would receive actual bank data.
- **Gap:** No import path for real bank statements. The `BankTransaction` model and reconciliation engine would accept a CSV loader, but none exists.

### 5.2 Approve / Reject has no undo, no audit trail, and no finalization

- **Question:** What does "approve" or "reject" actually mean in the close workflow? Does an approved flag mean "this is fine, close the books"? Does rejected mean "investigate" or "dismiss"?
- **Gap:**
  - No way to change a flag back to "open" without using Django admin.
  - No audit log of who approved/rejected what, or when.
  - No concept of a "closed" month — the status lives on individual flags and the summary, but there is no final "close the books" action.
  - Approved/rejected flags still disappear from the dashboard (only open flags are listed). Should there be a "resolved flags" view?

### 5.3 The LLM summary is read-only and not grounded in sources

- **Question:** How does a reviewer verify what the summary says? The current UI shows the summary text but does not link claims back to the underlying flags or transactions.
- **Gap:**
  - No citations from summary sentences to flag IDs or transactions.
  - No structured output from the LLM (free text only).
  - No guardrails beyond the deterministic fallback (no prompt versioning, no output schema, no content filtering).

### 5.4 Reconciliation matching is fuzzy but fixed

- **Current behavior:** exact vendor (case-insensitive), amount within $0.01, date within 1 day.
- **Question:** Is this the right tolerance for all companies and all transaction types? A $0.01 tolerance ignores fees and FX; a 1-day date tolerance misses weekend posting delays.
- **Gap:** No per-company or per-account tolerance configuration. No partial-match reporting (e.g., "matched by vendor and date but amount differs" vs. "completely unmatched").

### 5.5 Anomaly rules are simple but may be noisy

- **Question:** What is the expected false-positive rate? A new vendor or a one-off large expense is not always an anomaly.
- **Gap:**
  - No user-configurable thresholds.
  - No historical trend window configuration.
  - No way to mark a recurring anomaly as "expected" so it stops firing.

### 5.6 Multi-company UX is minimal

- **Question:** How does a user know which company is active? The selector shows `realm_id` (or an optional name), but there is no company onboarding, disconnection, or management UI beyond the OAuth flow.
- **Gap:**
  - No manual company name editing in the dashboard.
  - No way to disconnect or refresh a single company's OAuth token from the UI.
  - `QuickBooksCompany.name` is populated only if manually set in admin or if the code later fetches it from QuickBooks (currently deferred).

### 5.7 Deployment and operations are documented but not proven

- **Question:** Has the app ever actually been deployed to Railway, Render, or another host?
- **Gap:** `docs/DEPLOY.md` is a guide, not a validated runbook. Celery beat's `celerybeat-schedule` SQLite file can cause issues in ephemeral containers. No health-check endpoint, logging strategy, or monitoring is wired.

### 5.8 Access control is all-or-nothing

- **Current behavior:** any logged-in Django user can see every company and approve/reject any flag.
- **Question:** Should there be roles (viewer, reviewer, admin)? Should users be restricted to specific realms?
- **Gap:** No per-user, per-realm permissions. The Django admin is the only place to manage users.

### 5.9 Data retention and deletion are undefined

- **Question:** If a company is disconnected, should its transactions, flags, and summaries be deleted or archived?
- **Gap:** No retention policy, no soft-delete, no export before deletion.

---

## 6. How it fits together (data flow)

1. User connects QuickBooks via OAuth. Tokens and a `QuickBooksCompany` row are stored.
2. Nightly Celery beat (or manual dashboard action) runs `sync_quickbooks`, which pulls transactions and stores them with `realm_id`.
3. User optionally runs `generate_bank_feed` to create a test bank-side dataset for that month+realm.
4. User runs reconciliation from the dashboard or command line. The engine matches GL to bank and creates `Flag` rows.
5. Anomaly detection runs as part of reconciliation and creates additional `Flag` rows.
6. User reviews open flags in the dashboard and approves or rejects them.
7. User drafts a close summary. The agent reads open flags + category context and writes a draft.
8. User marks the summary reviewed. The `CloseSummary` status becomes `reviewed` and notes are saved.

---

## 7. Important files to know

| File / directory | What lives there |
|---|---|
| `core/models.py` | `Transaction`, `BankTransaction`, `Flag`, `CloseSummary`, `QBToken`, `QuickBooksCompany`. |
| `core/quickbooks/` | OAuth, token encryption, QuickBooks client, normalization, sync. |
| `core/bank_feed.py` | Synthetic bank-feed generator. |
| `core/reconciliation/engine.py` | Pandas-based GL↔bank matching and flag creation. |
| `core/anomaly/rules.py` | Rule-based anomaly detection. |
| `core/agent/summary.py` | LangGraph agent + deterministic fallback for close summaries. |
| `core/views.py` | Dashboard, OAuth, sync/reconcile/summary actions, flag approve/reject, summary review. |
| `core/urls.py` | URL routes. |
| `core/templates/core/` | HTMX templates for dashboard, flag rows, summary section. |
| `core/static/css/tokens.css` | Design tokens and ledger styling. |
| `core/tests/` | 148+ Django tests. |
| `docker-compose.yml`, `Dockerfile`, `.github/workflows/ci.yml` | Docker and CI configuration. |
| `docs/` | Plans, changelogs, deployment docs, this file. |

---

## 8. Suggested next questions to answer

If you are picking this project up, these are the highest-leverage clarifications:

1. Is the synthetic bank feed sufficient for the demo, or is a real bank-feed import (CSV/OFX/Plaid) the next priority?
2. What should the Approve/Reject actions mean for the close workflow, and do we need an audit log or a "close the month" finalization step?
3. Do we want the LLM summary to produce structured, citeable output, or is free-text good enough?
4. Should tolerances (amount/date) be configurable per company or account?
5. What is the target deployment host, and can we validate the deploy runbook end-to-end?
6. Do we need role-based access or per-realm permissions before a real user logs in?

---

## 9. Honest summary

The Monthly Close Assistant is a well-tested, internally consistent demo of an AI-assisted close workflow. It proves the integration points (QuickBooks, LLM, HTMX dashboard, Celery, Docker, CI) and it makes strong architectural choices (Postgres, rule-based anomaly detection, human-in-the-loop approval). Where it is weakest is in the transition from "demo" to "product": real bank feeds, audit trails, tolerances, roles, deployment hardening, and the semantics of approve/reject are still unresolved.
