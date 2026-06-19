# Monthly Close Assistant — Refactor Plan

**Status:** Planning exercise only. No code changes are proposed for immediate execution.  
**Date:** 2026-06-19  
**Branch audited:** `feature/close-assistant-build` (clean working tree)

---

## Step 1 — Audit (in full)

### 1.1 Module/package structure and conceptual architecture

The codebase advertises a conceptual pipeline:

> Data Sync Layer → Postgres → Analysis Engine → Agent Layer → Review Dashboard

The current package layout is:

```
core/
  __init__.py
  admin.py
  apps.py
  bank_feed.py
  models.py
  tasks.py
  templatetags/
  urls.py
  views.py
  agent/
    __init__.py
    reconcile.py      # AI-assisted account reconciliation suggestions + QB writes via core.quickbooks.writes
    summary.py        # Close-summary agent
  anomaly/
    __init__.py
    rules.py          # Vendor z-score, duplicate, new-vendor, category MoM
  quickbooks/
    __init__.py
    client.py         # OAuth, token refresh, sync, reports
    tokens.py         # Encryption + token persistence
    writes.py         # JournalEntry/Purchase/Deposit construction
  reconciliation/
    __init__.py
    engine.py         # Transaction/BankTransaction matching + balance-level flags
  management/commands/
    sync_quickbooks.py
    run_reconciliation.py
    generate_bank_feed.py
    generate_close_summary.py
    set_bank_balance.py
    seed_bank_balances.py
    suggest_account_fixes.py
    apply_account_fix.py
  migrations/
    0001_initial.py
    0002_qbtoken.py
    0003_quickbookscompany_banktransaction_realm_id_and_more.py
    0004_qbaccount.py
    0005_alter_flag_flag_type_bankstatementbalance_and_more.py
    0006_alter_bankstatementbalance_unique_together_and_more.py
    0007_flag_notes_accountreconciliationstate.py
  tests/
    test_agent.py
    test_agent_reconcile.py
    test_dashboard.py
    test_management.py
    test_models.py
    test_multi_company.py
    test_qb_writes.py
    test_quickbooks.py
    test_realm_scoping.py
    test_reconcile_commands.py
    test_reconciliation.py
    test_views.py
    (plus scaffold/deploy/docker/readme tests)
```

**Drift from the conceptual architecture**

- The **Agent Layer** (`core.agent`) is not read-only. `core.agent.reconcile.suggest_account_fixes` calls `core.quickbooks.client` and `core.quickbooks.writes.apply_suggestion` is invoked both from `core.views.reconcile_account_apply` and from `core.management.commands.apply_account_fix`. The agent is therefore entangled with QuickBooks write operations, which violates the stated design boundary.
- The **Analysis Engine** and **Review Dashboard** are blurred. `core.views.py` contains significant business logic: computing posted totals for bank balances (`_bank_balances_context`), orchestrating reconciliation + anomaly + summary + bank feed + QB apply flows, and deciding reconciliation status. This is controller/HTTP code doing engine work.
- **Data access** is scattered. Realm/company resolution (`QuickBooksCompany.objects.for_realm`) is used in nearly every module, and many functions take both `realm_id` and an optional `company` object, creating redundant lookups.

### 1.2 Business logic living in views.py

`core/views.py` currently contains the following engine-level responsibilities:

| Function | Business logic that belongs elsewhere |
|---|---|
| `reconcile_account_suggest` | Calls `suggest_account_fixes`, builds modal context. The view should only map HTTP parameters to a service call. |
| `reconcile_account_apply` | Decides dry-run vs. apply, invokes `qb_writes.apply_suggestion`, runs post-apply sync, updates `AccountReconciliationState`, updates flag audit notes. This is a complete write orchestration, not view logic. |
| `_bank_balances_context` | Computes `posted_total` by summing `Transaction.amount` for each `BankStatementBalance` row. This is reconciliation math that belongs in `core.reconciliation.engine` or a service layer. |
| `_dashboard_context` | Builds flag counts, summary lookups, has_data checks. Mostly view-appropriate, but flag aggregation could be centralized. |
| `qb_sync_now` | Wraps `qb_client.sync_transactions`. Acceptable thin wrapper, but error handling duplicates patterns elsewhere. |
| `reconcile_month` | Orchestrates `run_reconciliation` + `run_anomaly_detection`. Acceptable orchestration, but should ideally call a single service function. |
| `generate_bank_feed_view` | Wraps `generate_bank_feed`. Thin wrapper. |

The most problematic is `reconcile_account_apply`: it mixes HTTP parameter parsing, QuickBooks client construction, write execution, local DB sync, reconciliation state updates, and flag note updates in one 120-line view. This is the largest single candidate for extraction into a service layer.

### 1.3 Duplicated logic across engines

- **`_month_bounds`** is defined identically in:
  - `core/views.py:292`
  - `core/reconciliation/engine.py:40`
  - `core/anomaly/rules.py:40`
  - `core/bank_feed.py:54`
  - `core/agent/summary.py:57`
  - (`core/quickbooks/client.py:557` has `_month_bounds_for_query`, a string variant.)

- **`_prior_month`** is defined in `core/agent/summary.py:64` and `core/agent/reconcile.py:53` with identical logic.

- **`CASH_LIKE_ACCOUNT_TYPES = {"Bank", "Other Current Asset"}`** is duplicated in:
  - `core/views.py:57`
  - `core/bank_feed.py:35`
  - `core/management/commands/seed_bank_balances.py:23`

- **Posted-GL total for an account/month** is computed in at least three places:
  - `core/views.py:_bank_balances_context` (loop + `Sum`)
  - `core/reconciliation/engine.py:check_account_balances` (generator sum)
  - `core/agent/reconcile.py:gather_account_inputs` (generator sum)

- **Unmatched bank/GL detection** exists in `core/reconciliation/engine.py` (via DataFrame `matched` flags) and is recomputed in `core/agent/reconcile.py:gather_account_inputs` using ORM lookups.

- **LLM call plumbing** (`_call_llm`, `_call_anthropic_llm`, `_call_openai_llm`, provider selection) is duplicated between `core/agent/summary.py` and `core/agent/reconcile.py` with only minor naming differences.

- **Realm-id resolution** (`_resolve_realm_id` using `qb_tokens.get_active_token`) is duplicated in almost every management command.

### 1.4 Inconsistent naming

| Concept | Inconsistent names | Locations |
|---|---|---|
| Company/realm | `realm_id`, `company`, `QuickBooksCompany` | Throughout; some functions take `realm_id: str`, others take `company: QuickBooksCompany`, many take both. |
| External account id | `qb_account_id`, `account_id` | `BankStatementBalance.qb_account_id`, `QBAccount.account_id`, function args vary. |
| Internal account name | `account_name`, `gl_account`, `name` | `BankStatementBalance.account_name`, `Transaction.gl_account`, `QBAccount.name`. |
| Payee | `vendor`, `client_name` | `Transaction.vendor`, `BankTransaction.vendor`; no `client_name` currently, but the domain concept is payee/vendor throughout. |
| Suggestion identifier | `suggestion_id`, `suggestion_ids` | View uses `suggestion_ids`, command uses `--suggestion-id`. |
| Agent module | `summary` vs. `reconcile` | `core.agent.summary` (close summary) and `core.agent.reconcile` (account reconciliation). Naming is descriptive but `reconcile` collides with `core.reconciliation`. |
| Balance tolerance | `BALANCE_TOLERANCE` in engine, inline comparison in `reconcile_account_apply` | `core/reconciliation/engine.py` and `core/views.py` both check `abs(difference) <= BALANCE_TOLERANCE`. |

### 1.5 Missing or thin docstrings

Many public functions have good docstrings (notably `core/models.py`, `core/quickbooks/client.py`, `core/reconciliation/engine.py`). Gaps appear in:

- `core/views.py`
  - `_available_months`, `_request_realm_id`, `_render_dashboard`, `flag_approve`, `flag_reject`, `set_bank_balance`, `generate_bank_feed_view` have no docstrings or one-liners only.
  - `reconcile_account_suggest` and `reconcile_account_apply` docstrings do not document parameters or side effects.
- `core/bank_feed.py`
  - `_has_qbaccount_data`, `_cash_like_gl_account_names`, `_txns_to_dataframe` are private and reasonably named, but `_txns_to_dataframe` does not document the `prefix` parameter (which is unused).
- `core/agent/reconcile.py`
  - `_serialize_bank_row`, `_serialize_txn_row`, `_next_suggestion_id`, `_clean_suggestion`, `_parse_llm_json`, `_get_reconcile_provider` lack docstrings.
  - `_deterministic_suggestions` has a good docstring, but the internal accounting math is dense and uncommented.
- `core/agent/summary.py`
  - `_serialize_flag`, `_deterministic_summary`, `_get_summary_provider`, `_draft_node`, `_build_graph` lack docstrings.
- `core/quickbooks/writes.py`
  - `_make_ref`, `_account_ref_by_id`, `_lookup_suggestion` lack docstrings.
  - `create_purchase`/`create_deposit` do not document that they expect `category_account` to exist as a `QBAccount`.
- `core/quickbooks/tokens.py`
  - `_expiry` lacks a docstring.

### 1.6 Type hints

**Good coverage:** `core/models.py` is fully type-hinted. `core/quickbooks/client.py` and `core/reconciliation/engine.py` have decent coverage.

**Missing/incorrect:**

- `core/views.py`
  - Many view functions (`home`, `qb_oauth_start`, `qb_oauth_callback`, `dashboard`, `qb_sync_now`, `reconcile_month`, `draft_summary`, `flag_approve`, `flag_reject`, `set_bank_balance`, `generate_bank_feed_view`, `summary_review`) have no return type annotations.
  - `_dashboard_context` returns `dict` instead of `dict[str, Any]`.
  - `qb_api_client: Any | None = None` in `reconcile_account_suggest` is reasonable but could be tightened to a protocol.
- `core/quickbooks/client.py`
  - `refresh_and_store_tokens(qb_token) -> Any` should return `QBToken`.
  - `call_with_retry` returns `Any`; should be generic.
  - `store_tokens(auth_client: Any, ...)` should accept a protocol/typed object.
  - `normalize_record(record: Any, source_type: str) -> Optional[dict]` should return `Optional[dict[str, Any]]`.
  - `sync_transactions` returns `dict` instead of `dict[str, Any]`.
  - `pull_raw_records` returns `dict` instead of `dict[str, list[Any]]`.
  - `fetch_account_current_balances` returns `dict[str, dict[str, Any]]` but values contain `Decimal`.
- `core/quickbooks/tokens.py`
  - `store_tokens` returns `Any` (should be `QBToken`).
  - `get_active_token` returns untyped value.
  - `_expiry(now: Any, seconds: Optional[int])` lacks return type.
- `core/quickbooks/writes.py`
  - `create_journal_entry` `lines: list[dict]` should be `list[dict[str, Any]]`.
  - `apply_suggestion` takes `qb_client: QuickBooks` but tests pass `mock.MagicMock`, so the annotation is correct but not enforced.
- `core/bank_feed.py`
  - `generate_bank_feed` return type is `dict` (should be `dict[str, Any]`).
  - `_txns_to_dataframe(txns: list[Transaction])` should accept `QuerySet[Transaction] | list[Transaction]`.
- `core/agent/summary.py` and `core/agent/reconcile.py`
  - Heavy use of `Any` and `dict` without generic parameters (`dict[str, Any]`).
  - `llm: Optional[Any]` in both modules; should be a protocol or `Runnable` interface.

### 1.7 Error handling

**QuickBooks API calls**

| Call site | Timeout | Rate limit | Auth/token expiry | Malformed response | Notes |
|---|---|---|---|---|---|
| `qb_client.make_auth_client` | No | No | No | No | Raises `ValueError` for missing config; good. |
| `qb_client.get_authorization_url` | No | N/A | N/A | No | Session state setup; OK. |
| `qb_client.exchange_code_for_tokens` | No | No | No | No | Wrapped in `except Exception` in `views.qb_oauth_callback`; loses original error. |
| `qb_client.refresh_tokens` | No | No | No | No | Mutates `AuthClient`; no error handling if `refresh()` raises. |
| `qb_client.call_with_retry` | Yes (RetryableExceptions includes `TimeoutError`, but not `requests.Timeout` explicitly) | Partial (`QuickbooksException` catches many QBO errors, but not rate-limit specific) | Yes (`AuthorizationException` refresh once) | No | Best centralized retry logic in the codebase. |
| `qb_client.pull_raw_records` | Via `call_with_retry` | Via `call_with_retry` | Via `call_with_retry` | No | Returns dict of lists; malformed records are handled in `normalize_record`. |
| `qb_client.fetch_company_name` | Via `call_with_retry` | Via `call_with_retry` | Via `call_with_retry` | No | Catches all exceptions and returns `""`; acceptable best-effort. |
| `qb_client.sync_transactions` | Via `call_with_retry` | Via `call_with_retry` | Via `call_with_retry` | No | Catches all exceptions and returns error dict; good. |
| `qb_client.sync_accounts` | Via `call_with_retry` | Via `call_with_retry` | Via `call_with_retry` | No | Catches all exceptions and returns error dict; good. |
| `qb_client.fetch_account_current_balances` | Via `call_with_retry` | Via `call_with_retry` | Via `call_with_retry` | No | Catches all exceptions and returns `{}`; good. |
| `qb_client.fetch_general_ledger_summary` | Via `call_with_retry` | Via `call_with_retry` | Via `call_with_retry` | Yes (defensive parser) | Catches all exceptions and returns `{}`; good. |
| `qb_writes.create_*` (`.save()`) | No direct retry | No | No | No | Relies on `call_with_retry` upstream only if caller uses it. In `reconcile_account_apply` and `apply_account_fix`, the `.save()` calls are **not** wrapped in `call_with_retry`. |

**LLM API calls**

| Call site | Timeout | Rate limit | Auth/key error | Malformed response | Notes |
|---|---|---|---|---|---|
| `core.agent.summary._call_anthropic_llm` / `_call_openai_llm` | No | No | No (logs and returns `None` if key missing) | Yes (returns `[]` or falls back) | No explicit retry. `ImportError` handled. |
| `core.agent.reconcile._call_anthropic_llm` / `_call_openai_llm` | No | No | No | Yes | Same as above. Duplicate code. |

**Broad exception swallowing**

- `core/views.py` uses `except Exception:  # noqa: BLE001` in 9 places. In several cases this is justified (user-facing fallbacks), but it also swallows programming errors. Notable:
  - `reconcile_account_suggest` catches `Exception` when building the QB client and continues with `qb_api_client=None`; this is correct fallback behavior but should log at warning.
  - `reconcile_account_apply` catches `Exception` around the entire QB write block and renders the bank balances section with a notice. Correct user-facing behavior, but the rollback path is implicit.
  - `qb_oauth_callback` catches `Exception` around token exchange and returns a generic 400, discarding the actual error from logs/user.
  - `set_bank_balance` catches `Exception` when parsing `Decimal` and returns 400. This is too broad (`Decimal` construction failures are the only expected case).
- `core/agent/summary.py:136` and `core/agent/reconcile.py:171` catch `Exception` for best-effort QB balance fetch; acceptable.

**Celery context**

- `core/tasks.py:sync_quickbooks_task` calls `call_command("sync_quickbooks")` without any try/except. If the command raises `CommandError`, the task fails and Celery will retry depending on configuration, but no structured logging context is added.
- No task-level retry/backoff wrapper exists; retry relies entirely on `call_with_retry` inside the sync.

### 1.8 Test coverage gaps

| Module | Coverage | Gap |
|---|---|---|
| `core/models.py` | Good (`test_models.py` covers fields, constraints, choices, admin registration) | No tests for `QBToken.get_access_token`/`get_refresh_token` encryption integration beyond roundtrip. |
| `core/views.py` | Good for dashboard actions, OAuth, bank balances | No direct unit tests for `_bank_balances_context` math; only via dashboard render. No tests for `summary_review` beyond happy path. |
| `core/reconciliation/engine.py` | Good | `check_account_balances` idempotency is tested. No direct test for `_find_best_match` matching algorithm edge cases (multiple candidates, exact vs. closest). |
| `core/anomaly/rules.py` | Good | Rule functions are private (`_vendor_zscore_anomalies`, etc.) and tested via command. No unit tests for `_load_transactions_df` empty/edge cases. |
| `core/bank_feed.py` | Good via command | No direct tests for `generate_bank_feed`; only via `test_management.py`. |
| `core/agent/summary.py` | Good | LLM path tested with fake LLM; deterministic path tested. No test for `_build_graph` returning `None` when LangGraph missing. |
| `core/agent/reconcile.py` | Good | Deterministic suggestions tested. LLM parsing tested. No tests for `_clean_suggestion` edge cases (invalid posting type, missing line keys). No tests for `gather_account_inputs` when `qb_api_client` returns current balance. |
| `core/quickbooks/client.py` | Good | OAuth views tested via mocking. `call_with_retry` retry/backoff tested. No test for `fetch_general_ledger_summary` malformed report structures beyond minimal. No test for `sync_accounts` updating names/types. |
| `core/quickbooks/writes.py` | Good | JournalEntry/Purchase/Deposit tested with mocked `.save()`. No test for `apply_suggestion` dispatching purchase/deposit (only journal entry tested). |
| `core/quickbooks/tokens.py` | Good | Encryption roundtrip and plaintext fallback tested. |
| `core/management/commands/*` | Good | Commands are thin wrappers around functions that are tested elsewhere. |

**Notable gap:** There is no test proving that `reconcile_account_apply` (the view) handles partial QB write failures or post-apply sync failures gracefully. The test `test_apply_confirmation_calls_qb_and_refreshes_balances` only tests the happy path.

### 1.9 Dead code, unused imports, leftover scaffolding

**Likely dead/leftover:**

- `core/management/commands/sync_quickbooks.py` defines `--skip-reports` argument with help text "Skip fetching report summaries (currently unused; reserved for future report sync)". This is scaffolding for a feature that does not exist.
- `core/quickbooks/client.py` defines `refresh_tokens(auth_client)` which computes token datetimes but is **not called anywhere** in the codebase. `refresh_and_store_tokens` uses `store_tokens` directly after `auth_client.refresh()`. (Confirmed by searching; no references to `refresh_tokens` outside its own definition and tests.)
- `core/quickbooks/writes.py` defines `_lookup_suggestion` but it is not called within the module; the management command `apply_account_fix.py` defines its own `_lookup_suggestion`. So `core/quickbooks/writes.py:_lookup_suggestion` is dead code.
- `core/bank_feed.py:_txns_to_dataframe` accepts a `txns` parameter typed as `list[Transaction]` but is called with a QuerySet. It works because QuerySet is iterable, but the type hint is misleading.
- `core/bank_feed.py` `_has_qbaccount_data` is only used in `cash_only` mode; fine, but could be inlined.
- `core/management/commands/seed_bank_balances.py:116-119` has an empty `if not force: pass` block with a comment. Not dead code, but indicates the `--force` flag only affects reporting, not behavior (because `update_or_create` already updates). This is a UX inconsistency worth documenting or fixing.

**Unused imports** (surface-level scan):

- `core/views.py` imports `get_object_or_404` (used), `Q, Sum` (used), `FlagType`, `ReconciliationStatus` (used), etc. No obvious unused imports.
- `core/agent/reconcile.py` imports `DATE_TOLERANCE_DAYS` from `core.reconciliation.engine` but only `AMOUNT_TOLERANCE` and `_month_bounds` are used. `DATE_TOLERANCE_DAYS` is **not used** in `core/agent/reconcile.py`. (Confirmed via grep.)
- `core/quickbooks/writes.py` imports `Optional` from `typing` but does not use it.

**Migrations scaffolding:**

- Migrations `0003` through `0007` show significant schema evolution (multi-company, QBAccount, BankStatementBalance, Flag.notes, AccountReconciliationState). The accumulated sequence could be squashed into a single clean initial migration because the app is not yet in production. Migration `0003` includes a `_backfill_realm_id` RunPython and `0006` includes a `backfill_companies` RunPython; squashing would need to preserve these or drop them if the target environment has no pre-multi-company data.

---

## Step 2 — Refactor Plan

### 2.1 Architecture and layering

#### A. Extract a service layer for the account-reconciliation apply flow

- **What's wrong today:** `core/views.py:reconcile_account_apply` (lines 106-232) contains dry-run preview, QB client building, suggestion application, post-apply sync, state update, and flag note update. It is ~120 lines of view code doing business orchestration.
- **Proposed change:** Create `core/services/reconciliation.py` with `apply_account_reconciliation_suggestions(month, realm_id, qb_account_id, suggestion_ids, dry_run=True, user=None)`. This function would:
  - Validate inputs.
  - Call `reconcile_agent.suggest_account_fixes` to get suggestions.
  - In dry-run mode, return preview objects.
  - In apply mode, build the QB client, apply each selected suggestion via `qb_writes.apply_suggestion`, sync new transactions, run `run_reconciliation`, update `AccountReconciliationState`, and update the balance-reconciliation flag notes.
  - Return a structured result dict.
- **Rationale:** Makes the flow testable without HTTP, allows the management command and the view to share the same code path, and shrinks the view to parameter extraction and response rendering.
- **Effort/risk:** Medium. Touches `core/views.py`, new module, and requires updating `test_views.py` and `test_reconcile_commands.py` to exercise the service directly.

#### B. Extract bank-balance computation from views into the reconciliation engine

- **What's wrong today:** `_bank_balances_context` in `core/views.py:309-355` computes `posted_total` per balance by aggregating `Transaction.objects.filter(gl_account=balance.account_name)`. The same math exists in `check_account_balances` and `gather_account_inputs`.
- **Proposed change:** Add `core/reconciliation/engine.py:compute_posted_total(month, account_name, realm_id=None) -> Decimal`. Update `_bank_balances_context`, `check_account_balances`, and `gather_account_inputs` to call it.
- **Rationale:** Single source of truth for the control-side math; easier to test and optimize (e.g., add caching or a single grouped query).
- **Effort/risk:** Small. Pure code move with no behavior change.

#### C. Decouple the agent layer from QuickBooks writes

- **What's wrong today:** The "Agent Layer" can write to QuickBooks because `core.agent.reconcile.suggest_account_fixes` calls `core.quickbooks.client` and `core.quickbooks.writes.apply_suggestion` is invoked both from the view and command. There is no architectural barrier preventing a future contributor from adding `apply_suggestion` into `core.agent.reconcile`.
- **Proposed change:** 
  1. Move `apply_suggestion` and the `create_*` helpers from `core/quickbooks/writes.py` into a new `core/services/qb_writes.py` module. 
  2. Rename the agent module scope: `core.agent.reconcile` should only produce suggestions (read-only plus local state persistence). 
  3. Introduce an explicit import rule: `core.agent.*` modules are not allowed to import `core.services.qb_writes` or `core.quickbooks.client`. Enforce this via a simple architecture test (import introspection) or a `tox`/`pre-commit` check.
- **Rationale:** Makes the "no auto-approve / no direct QB write" boundary enforceable by import structure rather than convention.
- **Effort/risk:** Medium. Requires moving files, updating imports, and adding an architecture test.

#### D. Make each engine independently callable

- **Current state:**
  - Reconciliation: callable via `run_reconciliation` and `run_reconciliation` command. ✓
  - Anomaly detection: callable via `run_anomaly_detection` and invoked by `run_reconciliation` command. ✓
  - Close summary agent: callable via `draft_close_summary` and `generate_close_summary` command. ✓
  - Account-reconciliation agent: `suggest_account_fixes` is callable; apply is split between view and command. ✗
  - Bank feed generation: callable via `generate_bank_feed` and command. ✓
- **Proposed change:** After extracting the service layer (2.1.A), the apply flow becomes callable from both view and command. No other engine needs decoupling.

---

### 2.2 Organization

#### A. Proposed target package structure

```
core/
  models.py                  # Keep as single model module (Django convention).
  admin.py
  apps.py
  urls.py
  views.py                   # HTTP layer only: param extraction, auth, render.
  services/                  # Pure-Python orchestration, no HTTP.
    __init__.py
    reconciliation.py        # apply_account_reconciliation_suggestions, compute_posted_total
    close_summary.py         # orchestrate summary draft (thin wrapper today)
    qb_writes.py             # QuickBooks adjusting-entry writes (moved from core/quickbooks/writes.py)
  engines/                   # Analysis engines.
    __init__.py
    reconciliation.py        # merge core/reconciliation/engine.py here
    anomaly.py               # merge core/anomaly/rules.py here
    bank_feed.py             # move core/bank_feed.py here
  agents/                    # LLM/deterministic agents (read-only).
    __init__.py
    close_summary.py         # move core/agent/summary.py here
    account_reconcile.py     # move core/agent/reconcile.py here
  quickbooks/
    __init__.py
    client.py                # OAuth, token refresh, sync, reports (unchanged scope).
    tokens.py                # Encryption + persistence.
  management/commands/        # Keep; commands become thinner wrappers around services.
  migrations/
  tests/                      # Keep split per AGENTS.md.
```

**Alternative minimal target** (less disruptive): keep current package names but add `core/services/` and move duplicated helpers to `core/common/dates.py`, `core/common/constants.py`.

**Recommendation:** Adopt the minimal target first, then evaluate the full reorganization. The full reorganization is cleaner but touches many import paths and tests.

#### B. Domain grouping vs. technical-layer grouping

- **Why domain grouping should win:** The codebase is small (~3,500 LOC) and the domain boundaries (sync, reconciliation, anomaly, agent, dashboard) are clear. Technical-layer grouping (`models.py`, `views.py`, `utils.py`) already causes the current duplication because each engine reimplements its own date parsing and constants.
- **Specific moves:**
  - Create `core/common/dates.py` for `_month_bounds`, `_prior_month`, `_month_bounds_for_query`.
  - Create `core/common/constants.py` for `CASH_LIKE_ACCOUNT_TYPES`, `AMOUNT_TOLERANCE`, `DATE_TOLERANCE_DAYS`, `BALANCE_TOLERANCE`, anomaly thresholds.
  - Move QB write helpers to `core/services/qb_writes.py`.
  - Keep `models.py` as a single Django module (Django convention; splitting models across files is possible but adds complexity).

#### C. Centralize scattered constants/thresholds

- **Current scattered constants:**
  - `AMOUNT_TOLERANCE`, `DATE_TOLERANCE_DAYS`, `BALANCE_TOLERANCE` in `core/reconciliation/engine.py`.
  - `MIN_ZSCORE_SAMPLES`, `ZSCORE_THRESHOLD`, `DUPLICATE_WINDOW_DAYS`, `CATEGORY_MOM_THRESHOLD` in `core/anomaly/rules.py`.
  - `BANK_FEES_THRESHOLD`, `_DEFAULT_EXPENSE_ACCOUNT`, `_DEFAULT_INCOME_ACCOUNT`, `_DEFAULT_BANK_FEES_ACCOUNT` in `core/agent/reconcile.py`.
  - `AMOUNT_DELTAS`, `DATE_SHIFTS`, `EXTRA_VENDORS`, `CASH_LIKE_ACCOUNT_TYPES` in `core/bank_feed.py`.
  - `CASH_LIKE_ACCOUNT_TYPES` also in `core/views.py` and `core/management/commands/seed_bank_balances.py`.
- **Proposed change:** Move all tunable thresholds to `core/common/constants.py` (or Django settings with defaults). Keep engine-specific defaults in one discoverable location. For values that may vary per environment (e.g., z-score threshold, balance tolerance), read from `settings` with a constant default.
- **Rationale:** Prevents drift; makes A/B testing and per-realm tuning possible.
- **Effort/risk:** Small to medium. Requires updating imports across many files but no behavior change.

---

### 2.3 Naming and consistency

| Current | Standardized | Files to change |
|---|---|---|
| `realm_id` parameter + `company` parameter in same function | Use `company: QuickBooksCompany` as the canonical scoping object; derive `realm_id` when needed | `core/reconciliation/engine.py`, `core/anomaly/rules.py`, `core/agent/reconcile.py`, `core/agent/summary.py`, `core/bank_feed.py` |
| `qb_account_id` (balance/state) vs. `account_id` (QBAccount) | Use `qb_account_id` everywhere for the external QuickBooks account id | `core/models.py:QBAccount.account_id` could become `qb_account_id` (requires migration) or keep as `account_id` and standardize function args to `qb_account_id` |
| `gl_account` (Transaction) vs. `account_name` (BankStatementBalance) | Document that `gl_account` is the *name* of the GL account, not an id. Consider renaming to `gl_account_name` (migration required). | `core/models.py`, `core/reconciliation/engine.py`, `core/views.py`, `core/agent/reconcile.py` |
| `core.agent.reconcile` module | Rename to `core.agent.account_reconcile` to avoid collision with `core.reconciliation` | `core/agent/reconcile.py`, all imports, tests |
| Private `_month_bounds` copies | Rename public shared helper to `month_bounds` in `core/common/dates.py`; remove underscore prefix | All engine modules |
| `_resolve_realm_id` in every command | Extract to `core/management/commands/_utils.py` as `resolve_realm_id(options)` | All management commands |

**Function naming convention:**

- Adopt **verb-first** for side-effect functions and **noun-first** for pure queries.
- Examples:
  - `run_reconciliation` → keep (verb-first, side effects).
  - `check_account_balances` → keep (verb-first).
  - `gather_account_inputs` → keep (verb-first, but actually a query; could be `build_account_reconcile_inputs`).
  - `_load_dataframes` → `load_reconciliation_dataframes`.
  - `_bank_balances_context` → `build_bank_balances_context`.
  - `_available_months` → `list_available_months`.
  - `_default_realm_id` → `get_default_realm_id`.

**Files needing renames:**

- `core/reconciliation/engine.py` → `core/engines/reconciliation.py` (optional, see 2.2).
- `core/anomaly/rules.py` → `core/engines/anomaly.py`.
- `core/agent/summary.py` → `core/agents/close_summary.py`.
- `core/agent/reconcile.py` → `core/agents/account_reconcile.py`.
- `core/bank_feed.py` → `core/engines/bank_feed.py`.

---

### 2.4 Type hints and docstrings

#### A. Type hints

**High-volume gaps:**

- `core/views.py`: add return types to all view functions. Replace `dict` with `dict[str, Any]` and add `HttpResponse` return type.
- `core/quickbooks/client.py`: type the `qb_token` parameter as `QBToken | None` instead of `Optional[Any]`. Type `refresh_and_store_tokens` return as `QBToken`. Make `call_with_retry` generic using `TypeVar`.
- `core/quickbooks/tokens.py`: type `get_active_token` return as `QBToken | None`. Type `_expiry` return as `datetime | None`.
- `core/quickbooks/writes.py`: replace `list[dict]` with `list[dict[str, Any]]` and add return type dicts.
- `core/agent/summary.py` and `core/agent/reconcile.py`: replace `Optional[Any]` LLM parameters with a protocol:

```python
class LLMClient(Protocol):
    def invoke(self, prompt: str) -> object: ...
```

- `core/bank_feed.py`: type `generate_bank_feed` return as `dict[str, Any]` and `txns` parameter as `QuerySet[Transaction] | Iterable[Transaction]`.

#### B. Docstrings (prioritized)

**Highest priority (non-obvious side effects or assumptions):**

1. `core/views.py:reconcile_account_apply` — document parameters, dry-run behavior, side effects on `AccountReconciliationState`, `Flag.notes`, and QuickBooks.
2. `core/quickbooks/writes.py:apply_suggestion` — document the expected shape of `suggestion`, which `QBAccount` rows must exist, and the QB objects created.
3. `core/quickbooks/writes.py:create_purchase` / `create_deposit` — document that `category_account` must be a known active `QBAccount.name`.
4. `core/agent/reconcile.py:_deterministic_suggestions` — document the accounting math with examples.
5. `core/agent/reconcile.py:_clean_suggestion` — document the validation rules and why invalid suggestions are dropped.
6. `core/reconciliation/engine.py:_find_best_match` — document tie-breaking (exact amount, then closest amount, then closest date).

**Medium priority:**

- `core/views.py:_bank_balances_context`, `_dashboard_context`, `_render_dashboard`.
- `core/agent/summary.py:_deterministic_summary`, `_draft_node`.
- `core/quickbooks/client.py:normalize_record` — already documented, but could specify the `amount` semantics for `JournalEntry` (uses `TotalAmt`, not sum of lines).

**Low priority:**

- Simple getters/serializers (`_serialize_flag`, `_serialize_bank_row`, `_serialize_txn_row`).
- Private one-liners (`_next_suggestion_id`, `_make_ref`).

---

### 2.5 Error handling and resilience

#### A. Centralize retry/backoff for all external calls

- **What's wrong today:** `call_with_retry` in `core/quickbooks/client.py` is good for QuickBooks reads. However:
  - QB writes via `core/quickbooks/writes.py` do not use `call_with_retry`.
  - LLM calls have no retry/backoff at all.
- **Proposed change:** 
  1. Create `core/services/retry.py` with a generic `with_retry` decorator/context manager that handles exponential backoff, max attempts, and jitter.
  2. Wrap `qb_writes.create_journal_entry`, `create_purchase`, `create_deposit` `.save()` calls with `with_retry` for `QuickbooksException`, `ConnectionError`, `TimeoutError`.
  3. Wrap LLM `chain.invoke(...)` calls with `with_retry` for transient provider errors (timeout, rate limit).
- **Rationale:** Single place to tune retry policy; makes write path as resilient as read path.
- **Effort/risk:** Medium. Requires careful testing of retry behavior and ensuring idempotency of retried QB writes.

#### B. Handle token expiry explicitly in the apply flow

- **What's wrong today:** `reconcile_account_apply` builds a QB client directly; if the token is expired, the first API call fails and is caught generically. It does not use the proactive refresh in `call_with_retry`.
- **Proposed change:** After extracting the service layer, build the client through a helper that refreshes proactively, or call `.is_access_token_expired()` before the first write.
- **Effort/risk:** Small.

#### C. Improve OAuth callback error reporting

- **What's wrong today:** `core/views.py:qb_oauth_callback` catches `Exception` around token exchange and returns a generic "QuickBooks token exchange failed." message.
- **Proposed change:** Distinguish between configuration errors, network errors, and Intuit-reported errors. Log the original exception with context (realm_id, state match result) but keep the user-facing message generic for security.
- **Effort/risk:** Small.

#### D. Add structured logging context for Celery tasks

- **What's wrong today:** `core/tasks.py:sync_quickbooks_task` has no try/except or logging.
- **Proposed change:** Wrap `call_command` in a try/except that logs the exception with realm context and re-raises so Celery can retry. Add `bind=True` to access `self.request.id` for tracing.
- **Effort/risk:** Small.

---

### 2.6 Idempotency — verify, don't assume

**Existing idempotency tests:**

| Flow | Test | Verdict |
|---|---|---|
| `sync_transactions` | `test_second_run_is_idempotent` in `test_quickbooks.py` | ✓ Explicit |
| `run_reconciliation` | `test_reconciliation_is_idempotent` in `test_management.py` | ✓ Explicit |
| `check_account_balances` | `test_idempotent_runs_replace_existing_balance_flag` in `test_reconciliation.py` | ✓ Explicit |
| `run_anomaly_detection` | `test_anomaly_detection_is_idempotent` in `test_management.py` | ✓ Explicit |
| `draft_close_summary` | `test_re_running_updates_existing_summary` in `test_agent.py` | ✓ Explicit (asserts one row, same id) |
| `generate_bank_feed` | `test_force_flag_overwrites` in `test_management.py` | Partial: asserts count stable with `--force`, but does not assert identical resulting state without force (it expects a `CommandError`). |

**Missing idempotency tests:**

1. **`reconcile_account_apply` dry-run path:** Running the same dry-run twice should not create or modify any database rows. Currently untested.
2. **`reconcile_account_apply` apply path:** Running the same apply twice (with the same suggestions selected) should not create duplicate QB objects. This is hard to test without a sandbox, but the local state (`AccountReconciliationState.applied_suggestions`) should prevent re-application. Currently untested.
3. **`seed_bank_balances`:** Running twice without `--force` should leave the same row count and values. Currently untested.
4. **`set_bank_balance` (command and view):** Running twice with the same inputs should result in one row with the latest value. Currently untested.
5. **`generate_bank_feed` with `force=True` and fixed seed:** Running twice with the same seed should produce identical bank transaction counts and matching IDs (or at least the same number of rows). Currently only count is asserted.

**Proposed additions:**

- Add explicit "run twice, assert identical state" tests for the missing flows.
- For QB-write flows, add tests that verify `applied_suggestions` deduplication and that the service returns a clear result when suggestions were already applied.

---

### 2.7 Dead code and cleanup

#### A. Remove unused `refresh_tokens` function

- **Location:** `core/quickbooks/client.py:226-243`
- **Confirmation:** Grep shows no non-test references.
- **Action:** Delete the function and its tests in `test_quickbooks.py` (`RefreshTokensTests` class).

#### B. Remove unused `_lookup_suggestion` in `core/quickbooks/writes.py`

- **Location:** `core/quickbooks/writes.py:190-194`
- **Confirmation:** Not called within the module; management command defines its own.
- **Action:** Delete `core/quickbooks/writes.py:_lookup_suggestion`.

#### C. Remove `--skip-reports` scaffolding from `sync_quickbooks`

- **Location:** `core/management/commands/sync_quickbooks.py:38-40`
- **Action:** Remove the argument and update help text. It is misleading because it does nothing.

#### D. Remove unused `DATE_TOLERANCE_DAYS` import

- **Location:** `core/agent/reconcile.py:30`
- **Action:** Remove from the import from `core.reconciliation.engine`.

#### E. Remove unused `Optional` import

- **Location:** `core/quickbooks/writes.py:12`
- **Action:** Remove `Optional`.

#### F. Clarify or remove empty `pass` block in `seed_bank_balances`

- **Location:** `core/management/commands/seed_bank_balances.py:116-119`
- **Action:** Either remove the empty block (the comment explains behavior) or make `--force` actually meaningful. Given the current behavior (always update), the simplest fix is to delete the empty `if not force: pass`.

#### G. Remove `_month_bounds` duplicates

- **Action:** After moving to `core/common/dates.py`, delete the duplicate definitions.

---

### 2.8 Best practices pass

#### A. Replace raw loops and generator sums with querysets where possible

- **`core/views.py:_bank_balances_context`** (line 325-330): loops over `balances_qs` and runs one aggregate query per balance. For many accounts this is N+1.
  - **Fix:** Compute all posted totals for the month in a single grouped query: `Transaction.objects.filter(date__range=(first, last), realm_id=realm_id).values('gl_account').annotate(total=Sum('amount'))`.
- **`core/reconciliation/engine.py:check_account_balances`** (line 140-150): loops over `balances_qs` and fetches all transactions per balance.
  - **Fix:** Same grouped query approach, then match by `account_name`/`gl_account`.
- **`core/agent/reconcile.py:gather_account_inputs`** (line 125): `sum((txn.amount for txn in posted_txns), start=Decimal("0"))`. 
  - **Fix:** Use `posted_txns.aggregate(total=Sum('amount'))['total'] or Decimal('0')`.
- **`core/agent/reconcile.py:unmatched_gl`** (line 132-138): loops all GL transactions and calls `.bank_transactions.count()` per row.
  - **Fix:** Use `Count('bank_transactions')` annotation and filter where `bank_transactions__count=0`.

#### B. Add missing `select_related` / `prefetch_related`

- **`core/views.py:_dashboard_context`** already uses `select_related` for flags (line 370). Good.
- **`core/agent/reconcile.py:gather_account_inputs`** fetches `bank_rows` then iterates `bank.matched_transaction_id` without `select_related`. 
  - **Fix:** `BankTransaction.objects.filter(...).select_related('matched_transaction_id')`.
- **`core/anomaly/rules.py:_vendor_zscore_anomalies`** issues a historical query per vendor. Could use `Prefetch` or a single grouped query, but the current per-vendor approach is acceptable for small data.

#### C. Model-level uniqueness constraints

- Current constraints use `unique_together` (older Django style). 
  - **Proposed change:** Migrate to `UniqueConstraint` with `models.UniqueConstraint` in `Meta.constraints`. This is a Django best practice and supports conditional uniqueness in the future.
- `QBToken` has `related_name="token"` on the FK to `QuickBooksCompany`, which is singular but returns a queryset. 
  - **Proposed change:** Rename to `"tokens"` (requires migration).
- `Transaction.qb_transaction_id` plus `company` uniqueness is enforced. Good.
- `BankStatementBalance` unique on `(company, qb_account_id, month)`. Good.

#### D. Secrets logging check

- **Finding:** No secrets are logged at debug/info/warning/error levels. `QBTokenAdmin` excludes encrypted fields from display. Good.
- **Caveat:** `core/quickbooks/tokens.py` has a plaintext fallback when `QB_TOKEN_ENCRYPTION_KEY` is unset, which emits a `warnings.warn`. This is acceptable for local dev but must not be used in production.
- **Recommendation:** Add a system check or startup warning in production if `QB_TOKEN_ENCRYPTION_KEY` is missing.

#### E. Migration squashing

- The migrations from `0001` to `0007` show significant churn. Because the app is not in production, consider squashing to a single migration once the model set stabilizes.
- **Caveat:** Migrations `0003` and `0006` contain data migrations (`_backfill_realm_id`, `backfill_companies`). If squashing, decide whether to preserve them or assume no legacy NULL data exists. For a pre-production portfolio project, dropping the data migrations is reasonable.
- **Effort/risk:** Medium. Requires regenerating migrations and verifying tests pass after `migrate --fake` or rebuild.

---

## Recommended Sequence

The refactor should be done in small, green-test increments. Recommended order:

1. **Dead code cleanup** (2.7.A-F) — small, safe, establishes clean baseline.
2. **Centralize dates and constants** (2.2.C, 2.3 naming for helpers) — removes duplication, low risk.
3. **Type hints and docstrings pass** (2.4) — no behavior change, improves maintainability.
4. **Extract `compute_posted_total` and grouped queries** (2.1.B, 2.8.A) — improves performance and removes duplication.
5. **Extract service layer for apply flow** (2.1.A) — medium risk; share code between view and command.
6. **Move QB write helpers to `core/services/qb_writes.py`** (2.1.C) — enforces agent-layer boundary.
7. **Centralize retry/backoff** (2.5.A) — medium risk; requires thorough retry tests.
8. **Add missing idempotency tests** (2.6) — verifies correctness of above changes.
9. **Package reorganization** (2.2.A full target) — highest risk; do last after everything is green.
10. **Migration squash** (2.8.E) — do after model/package structure is final.

**Dependencies:**

- 2.1.A depends on 2.1.B (compute posted total should be stable before moving apply flow).
- 2.1.C depends on 2.1.A (service layer determines where QB writes live).
- 2.5.A depends on 2.1.C (retry wraps QB writes after they are centralized).
- 2.8.E (migration squash) should happen after 2.2.A (package reorganization) if model moves occur.

---

## Open Questions

These need a product/design decision before planning further:

1. **Agent write boundary strictness:** Should `core.agent.*` modules be *forbidden by import rule* from touching QB writes, or is it acceptable for an agent module to provide a `suggest_and_apply` orchestration function as long as it delegates to `core.services.qb_writes`? This affects whether 2.1.C is a hard architectural rule or a soft convention.
2. **Renaming `QBAccount.account_id` to `qb_account_id`:** This is a clearer name but requires a migration and updates many queries/tests. Is the migration churn worth the naming clarity?
3. **Renaming `Transaction.gl_account` to `gl_account_name`:** Same trade-off as above.
4. **`--force` semantics in `seed_bank_balances`:** Currently `--force` is effectively a no-op because `update_or_create` always updates. Should `--force` be removed, or should it change behavior to skip existing rows unless forced?
5. **Package reorganization scope:** Do we adopt the full `core/services/`, `core/engines/`, `core/agents/` structure, or only add `core/services/` and `core/common/` to minimize disruption?
6. **LLM abstraction:** Should the duplicated LLM call code be extracted into `core/services/llm.py`? This adds a new module but removes the most obvious duplication between summary and account-reconcile agents.
7. **Migration squash:** Given this is a portfolio project with no production data, can we squash all migrations into `0001_initial.py` and delete the data migrations?

---

## Explicitly Out of Scope

The following were noticed but are deliberately not included in this refactor plan:

1. **Adding real bank-feed integration** — The current `core/bank_feed.py` is a synthetic testing helper. Replacing it with a real bank API or file importer is a feature, not a refactor.
2. **Adding real-time dashboard updates (WebSockets/SSE)** — HTMX partial swaps are sufficient for the current scope.
3. **Implementing the `--skip-reports` feature** — Removed as dead scaffolding; actual report sync is a future feature.
4. **Changing the LLM provider strategy** — We will consolidate call plumbing but not change the model selection logic or add new providers.
5. **Production hardening beyond the scope of this exercise** — e.g., full audit logging, RBAC, SOC-2 controls. Noted as future work.
6. **Splitting `core/models.py` into a package** — Django supports this, but it adds complexity with little gain for ~9 models. Kept as single module.
7. **Adopting async views or Django Ninja** — Out of scope; current function-based views + HTMX are intentional.

---

**End of plan.**
