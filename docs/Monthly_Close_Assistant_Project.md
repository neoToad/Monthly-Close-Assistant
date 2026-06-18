# Monthly Close Assistant — Project Plan

## Why This Project
Built to address a specific interview gap: lack of accounting automation experience for the AI Agent Builder role. 

## Project Summary
An AI-assisted reconciliation and close-summary tool that pulls data from the QuickBooks Sandbox API, reconciles it against a bank-side dataset, flags anomalies, and uses an LLM agent to draft a plain-language monthly close summary for human review.

**Working name:** Close Copilot (or Monthly Close Assistant)

---

## ELI5 Explanation
The agent is like a fast, careful helper that:
1. Checks if two lists that are supposed to match (bank records vs. accounting records) actually match — flags anything off
2. Spots unusual transactions (way bigger than normal, duplicates, new vendors with no history)
3. Writes a plain-English summary of what changed and what needs review
4. Never decides or fixes anything on its own — a human always has final approval

---

## Architecture

```
QuickBooks API → Data Sync Layer → PostgreSQL → Analysis Engine → Agent Layer → Review Dashboard (HTMX)
```

- **Data Sync Layer** (Django/Python): pulls transactions and GL entries from QuickBooks, normalizes into internal schema
- **PostgreSQL**: stores normalized transactions, GL entries, and flags raised by the analysis engine
- **Analysis Engine** (Pandas/NumPy): runs reconciliation and anomaly detection
- **Agent Layer** (CrewAI or LangGraph + LLM API): generates a draft close summary from flagged items and context
- **Review Dashboard** (Django + HTMX): displays flags and draft summary, lets a "CFO" approve/reject

---

## Tech Stack

| Layer | Tool |
|---|---|
| Backend | Django (server-rendered views, no separate API layer) |
| Data source | QuickBooks Sandbox API (OAuth 2.0) |
| Database | PostgreSQL |
| Analysis | Pandas, NumPy |
| Agent | CrewAI or LangGraph + LLM API |
| Jobs | Celery (scheduled data sync) |
| Frontend | HTMX + Django templates |
| Deploy | Docker, Railway or DigitalOcean, GitHub Actions CI/CD |

**Why HTMX instead of React:** deliberate architecture choice for an internal review tool — server-rendered simplicity with partial-page updates instead of building and maintaining a separate API + SPA. Good interview talking point about making the right call for the use case, not defaulting to the flashiest tool.

---

## Core Features

### 1. Data Ingestion
Pull transactions, GL entries, accounts, and vendors from QuickBooks Sandbox via REST API (key endpoints: `Transactions/JournalEntry`, `Purchase`, `Deposit`, `Account`).

### 2. Bank Feed for Reconciliation
QuickBooks sandbox data represents the "recorded" (GL) side. A separate "bank" dataset is needed to reconcile against.

**Implementation:** For production use the bank side would come from a bank integration or an uploaded statement. For development and testing, the app includes an optional synthetic bank-feed generator that derives rows from the QuickBooks data and introduces configurable discrepancies:
- Drop ~5% of transactions (missing from bank)
- Duplicate ~3% (bank shows it twice)
- Shift amounts slightly on ~4% (rounding/fee differences)
- Shift dates by 1–2 days on ~5% (posting vs. transaction date)
- Add a few bank-only transactions with no QuickBooks match

This synthetic feed remains useful as a testing tool to validate the reconciliation engine against known ground truth.

### 3. Reconciliation Check
Compare bank-side transactions against GL-recorded entries. Flag mismatches in amount, date, or vendor beyond a tolerance, and flag entries present on only one side.

### 4. Anomaly Detection
Keep rules simple and explainable (not ML-heavy) so they're easy to describe in an interview:
- Transaction amount more than X standard deviations from that vendor's historical average
- Duplicate transactions (same vendor, amount, week)
- New vendor with no transaction history
- Large month-over-month category swing (e.g., software spend up 300%)

### 5. Agent Summary Generation
Feed the agent flagged items plus context (prior month totals, category breakdowns). Prompt it to draft a close summary: what changed, what's flagged, why.

**Hard boundary:** the agent is strictly a draft generator, never a final approver. No auto-posting journal entries, no write actions back to QuickBooks, read-and-flag only. This boundary is a selling point in interviews, not a limitation.

### 6. Review Dashboard (HTMX)
- Table of flagged items (transaction, flag reason, amount, date) with `hx-post` approve/reject buttons that swap the row's status in place, no full reload
- Agent's draft summary rendered as a template block, with an `hx-post` "mark reviewed" action
- Month selector that triggers `hx-get` to reload the flagged items table, no page refresh

---

## Optional Stretch Features
- Category trend chart (spend by category month-over-month) for visual backup on flags
- Memory across months — store each month's close so the agent compares against rolling history instead of one snapshot
- Audit log — table logging every flag raised and whether a human approved/rejected it
- Export approved summary as PDF/doc

---

## Suggested Build Order
1. QuickBooks sandbox OAuth setup + pull raw data into Postgres
2. Generate a synthetic bank feed for testing reconciliation (optional)
3. Reconciliation logic
4. Anomaly detection rules
5. Agent summary generation (CrewAI or LangGraph)
6. HTMX review dashboard
7. Deploy (Docker, Railway/DigitalOcean, GitHub Actions)

---

## Interview Positioning
- **Project description for portfolio/resume:** "An AI-assisted reconciliation and close-summary tool that flags discrepancies and drafts a close report for human review, built against the QuickBooks API."
- **Key talking points:**
  - Deliberate human-in-the-loop design for financial-context AI
  - Explainable, rule-based anomaly detection rather than an opaque ML model
  - Testing rigor: includes a synthetic bank feed with known discrepancies to validate reconciliation logic against ground truth
  - Architecture choice of HTMX over React/SPA for an internal tool — simplicity matched to use case
  - Direct relevance to medical billing background: compliance-sensitive financial data, process accuracy, revenue cycle exposure
