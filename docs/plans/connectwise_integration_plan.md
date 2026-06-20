# Plan: ConnectWise-to-QBO Reconciliation (Test/Mock Integration)

**Status:** Draft / ready for implementation  
**Date:** 2026-06-20  

## Goal

Add a **mock/test integration** that reconciles ConnectWise activity against QuickBooks Online invoices to surface two distinct revenue/margin problems:

1. **Hourly / T&M clients:** unbilled time, expenses, or products that were recorded in ConnectWise but not invoiced through QBO.
2. **Flat-fee / managed services clients:** margin erosion where the cost-to-serve (hours × burden rate + expenses + products) approaches or exceeds the fixed monthly fee from QBO.

This is a **test/simulator-first** build. No live ConnectWise API is required; synthetic data is generated via a `generate_connectwise_feed` management command that mirrors the existing `generate_bank_feed` pattern.

## Problem statement

The existing reconciliation engine compares the QuickBooks GL (`Transaction`) to a bank feed (`BankTransaction`). It does not look at the operational source of work (ConnectWise time/expenses/products) versus the revenue actually invoiced in QBO.

For a professional services / MSP workflow, this creates two blind spots:

* **Revenue leakage:** technicians log billable hours in ConnectWise, but the month's QBO invoice does not reflect all of it.
* **Margin erosion:** fixed-price agreements look healthy on the invoice side, but labor and pass-through costs consume the margin.

This plan adds the missing operational-to-financial reconciliation layer.

## Design decisions (from 2026-06-20 review)

| Topic | Decision |
|---|---|
| ConnectWise data source | Synthetic `generate_connectwise_feed` management command; CSV import out of scope for MVP |
| Billing model detection | Manual `ClientMapping.billing_model` (`hourly`, `flat_fee`, `retainer`) |
| Burden rates | Config table `ConnectWiseWorkRole` with global default fallback |
| Client name matching | Manual `ClientMapping` first; fuzzy helper considered future work |
| Cost-to-serve scope | Time + expenses + products, additive, with detail breakdown in flag reason |
| QBO revenue side | Add `Invoice` / `InvoiceLine` ingestion from QBO; use **total invoice amount per customer/month** |
| ConnectWise agreement detail | `agreement_name` only |
| Margin thresholds | Global settings for target/warn/critical margin |
| Timing | Same-month comparison; documented MVP limitation |
| Dashboard location | New **"Client Reconciliation"** section below bank balances |

## Proposed changes

### 1. Add QBO customer master data

New model `QBCustomer` (parallel to `QBAccount`):

```python
class QBCustomer(models.Model):
    company = ForeignKey(QuickBooksCompany)
    realm_id = CharField
    customer_id = CharField  # QBO customer id
    name = CharField
    active = BooleanField(default=True)

    class Meta:
        unique_together = [["company", "customer_id"]]
```

* Sync QBO customers during `sync_quickbooks` (unless `--skip-customers`).
* Store customer name/id so `ClientMapping` and invoice ingestion can reference a stable row.

### 2. Add ConnectWise master data models

```python
class ConnectWiseCompany(models.Model):
    company = ForeignKey(QuickBooksCompany)
    realm_id = CharField
    connectwise_id = CharField
    name = CharField

    class Meta:
        unique_together = [["company", "connectwise_id"]]


class ClientMapping(models.Model):
    company = ForeignKey(QuickBooksCompany)
    realm_id = CharField
    connectwise_company = ForeignKey(ConnectWiseCompany)
    qbo_customer = ForeignKey(QBCustomer)
    billing_model = CharField(choices=["hourly", "flat_fee", "retainer"])
    flat_fee_amount = DecimalField(null=True, blank=True)
    default_burden_rate = DecimalField(null=True, blank=True)

    class Meta:
        unique_together = [["company", "connectwise_company"], ["company", "qbo_customer"]]


class ConnectWiseWorkRole(models.Model):
    company = ForeignKey(QuickBooksCompany)
    realm_id = CharField
    role_name = CharField
    burden_rate = DecimalField

    class Meta:
        unique_together = [["company", "role_name"]]
```

`ClientMapping.flat_fee_amount` is used as the MRR/revenue target for flat-fee reconciliation.

`ConnectWiseWorkRole.burden_rate` is used for time-based cost-to-serve. A global default burden rate is read from Django settings (`CONNECTWISE_DEFAULT_BURDEN_RATE`) and used when no role-specific rate exists.

### 3. Add QBO invoice ingestion

Extend `core/quickbooks/client.py` to pull `Invoice` records for the configured realm and normalize them into two new models:

```python
class Invoice(models.Model):
    company = ForeignKey(QuickBooksCompany)
    realm_id = CharField
    qb_invoice_id = CharField
    customer = ForeignKey(QBCustomer)
    customer_name = CharField  # denormalized
    invoice_date = DateField
    total_amount = DecimalField
    source_type = "Invoice"


class InvoiceLine(models.Model):
    company = ForeignKey(QuickBooksCompany)
    realm_id = CharField
    invoice = ForeignKey(Invoice)
    line_number = IntegerField
    description = TextField(blank=True)
    amount = DecimalField
    service_item = CharField(blank=True)
```

For the MVP, reconciliation uses **invoice totals per customer/month** from `Invoice.total_amount`, not line-level matching. `InvoiceLine` is ingested for future use and detail display.

Update `sync_quickbooks` to call a new `sync_invoices` helper and a `sync_customers` helper.

### 4. Add ConnectWise activity models

```python
class TimeEntry(models.Model):
    company = ForeignKey(QuickBooksCompany)
    realm_id = CharField
    connectwise_entry_id = CharField  # idempotency key
    connectwise_company = ForeignKey(ConnectWiseCompany)
    agreement_name = CharField(blank=True)
    ticket_number = CharField(blank=True)
    technician = CharField
    date = DateField
    hours = DecimalField
    billable_rate = DecimalField(null=True)
    work_role = CharField(blank=True)
    is_billable = BooleanField(default=True)


class ExpenseEntry(models.Model):
    company = ForeignKey(QuickBooksCompany)
    realm_id = CharField
    connectwise_entry_id = CharField
    connectwise_company = ForeignKey(ConnectWiseCompany)
    agreement_name = CharField(blank=True)
    date = DateField
    amount = DecimalField
    description = CharField(blank=True)


class ProductEntry(models.Model):
    company = ForeignKey(QuickBooksCompany)
    realm_id = CharField
    connectwise_entry_id = CharField
    connectwise_company = ForeignKey(ConnectWiseCompany)
    agreement_name = CharField(blank=True)
    date = DateField
    amount = DecimalField
    description = CharField(blank=True)
```

All three models are scoped to `(company, connectwise_entry_id)` for idempotency.

### 5. Add synthetic ConnectWise feed generator

New module `core/engines/connectwise_feed.py` and command `core/management/commands/generate_connectwise_feed.py`.

```bash
python manage.py generate_connectwise_feed 2025-01 \
    --realm-id realm-a \
    --scenario hourly_leakage \
    [--force] \
    [--seed 123]
```

Supported scenarios:

* `hourly_leakage` — billable time not fully invoiced in QBO
* `flat_fee_profitable` — cost-to-serve well below MRR
* `flat_fee_margin_erosion` — cost-to-serve approaching MRR
* `flat_fee_loss` — cost-to-serve exceeds MRR
* `missing_mapping` — ConnectWise company has no `ClientMapping`
* `mixed` — random mix across clients

Scenario data comes from fixture files under `core/fixtures/connectwise_scenarios/`:

```json
[
  {
    "connectwise_company_name": "Acme Corp",
    "qbo_customer_name": "Acme Corp",
    "billing_model": "hourly",
    "flat_fee_amount": null,
    "time_entries": [...],
    "expense_entries": [...],
    "product_entries": [...]
  }
]
```

The generator:

1. Creates `ConnectWiseCompany` rows from the fixture.
2. Creates `ClientMapping` rows for mapped clients.
3. Creates `TimeEntry`, `ExpenseEntry`, and `ProductEntry` rows.
4. Does **not** create QBO invoices; those come from `sync_quickbooks` or another simulator command.

A companion command `generate_qbo_invoices` (or extension to `generate_connectwise_feed` with `--generate-invoices`) creates matching `Invoice` rows so the reconciliation engine has both sides. This keeps the simulator self-contained for tests.

### 6. Add the reconciliation engine

New module `core/engines/connectwise_reconciliation.py`:

```python
def run_connectwise_reconciliation(month: str, realm_id: Optional[str] = None) -> dict:
    """Compare ConnectWise activity to QBO invoices per client/month.

    Creates flags for:
    - Unbilled time/expenses/products (hourly/retainer clients)
    - Margin erosion or loss (flat-fee clients)
    - Missing ClientMapping
    """
```

Per-client calculation:

```
cw_billable   = SUM(time.hours × time.billable_rate) + expenses + products
cw_cost       = SUM(time.hours × burden_rate) + expenses + products
qbo_invoiced  = SUM(Invoice.total_amount for customer in month)

if billing_model in ("hourly", "retainer"):
    leakage = cw_billable - qbo_invoiced
    flag if leakage > threshold

if billing_model == "flat_fee":
    revenue = ClientMapping.flat_fee_amount
    margin_dollars  = revenue - cw_cost
    margin_percent  = margin_dollars / revenue
    flag if margin_percent < threshold
```

Thresholds from Django settings (with safe defaults):

```python
CONNECTWISE_UNBILLED_THRESHOLD = Decimal("100.00")
CONNECTWISE_TARGET_MARGIN = Decimal("0.35")      # 35%
CONNECTWISE_MARGIN_WARN = Decimal("0.20")        # 20%
CONNECTWISE_MARGIN_CRITICAL = Decimal("0.00")    # 0% or negative
```

Flag reasons include the detail breakdown, e.g.:

> "Acme Corp (flat-fee, MRR $5,000): cost-to-serve $4,200 = labor $3,200 + expenses $600 + products $400. Margin $800 (16%) below 20% warning threshold."

> "Beta LLC (hourly): ConnectWise billable $8,500; QBO invoiced $6,200. Unbilled leakage $2,300."

### 7. Add new flag types

Extend `core/models.py` `FlagType`:

```python
CONNECTWISE_UNBILLED = "connectwise_unbilled", "ConnectWise Unbilled"
CONNECTWISE_MARGIN = "connectwise_margin", "ConnectWise Margin Erosion"
CONNECTWISE_MISSING_MAPPING = "connectwise_missing_mapping", "ConnectWise Missing Mapping"
```

Flags are created with severity:

* `CONNECTWISE_UNBILLED` — `HIGH` if leakage > 2× threshold, else `MEDIUM`
* `CONNECTWISE_MARGIN` — `HIGH` at/below 0% margin, `MEDIUM` below warn threshold, `LOW` below target
* `CONNECTWISE_MISSING_MAPPING` — `MEDIUM`

### 8. Add management command

`core/management/commands/run_connectwise_reconciliation.py`:

```bash
python manage.py run_connectwise_reconciliation 2025-01 --realm-id realm-a
```

Runs the engine and prints a summary:

```
ConnectWise reconciliation complete for 2025-01:
  Clients checked: 8
  Unbilled flags: 2
  Margin flags: 1
  Missing mappings: 1
```

### 9. Add dashboard section

New view `connectwise_reconciliation_view` wired to `POST /dashboard/connectwise/reconcile/`.

Update `core/templates/core/dashboard_content.html` to add a **"Client Reconciliation"** section below the bank balances panel:

* Button **"Run ConnectWise Reconciliation"**
* Button **"Generate ConnectWise Test Feed"**
* Summary cards:
  * Clients checked
  * Unbilled leakage total
  * Flat-fee clients below margin target
  * Missing mappings
* Table of flags limited to the new ConnectWise flag types

The existing bank balances section and reconciliation workflow remain untouched.

### 10. Add mapping UI (minimal)

For the MVP, `ClientMapping` rows are created by the synthetic generator. A simple dashboard readout shows any `ConnectWiseCompany` without a mapping.

A future plan can add a mapping modal. For now, document that mappings can be seeded via admin or fixture.

## Files touched

### New files

* `core/engines/connectwise_reconciliation.py`
* `core/engines/connectwise_feed.py`
* `core/management/commands/generate_connectwise_feed.py`
* `core/management/commands/run_connectwise_reconciliation.py`
* `core/fixtures/connectwise_scenarios/hourly_leakage.json`
* `core/fixtures/connectwise_scenarios/flat_fee_profitable.json`
* `core/fixtures/connectwise_scenarios/flat_fee_margin_erosion.json`
* `core/fixtures/connectwise_scenarios/flat_fee_loss.json`
* `core/fixtures/connectwise_scenarios/missing_mapping.json`
* `core/fixtures/connectwise_scenarios/mixed.json`
* `core/tests/test_connectwise_reconciliation.py`
* `core/tests/test_connectwise_feed.py`
* `core/tests/test_qbo_invoice_sync.py` (or extend `test_views.py`)

### Modified files

* `core/models.py` — add `QBCustomer`, `ConnectWiseCompany`, `ClientMapping`, `ConnectWiseWorkRole`, `Invoice`, `InvoiceLine`, `TimeEntry`, `ExpenseEntry`, `ProductEntry`; extend `FlagType`.
* `core/migrations/0001_initial.py` — include all new tables in the squashed migration.
* `core/quickbooks/client.py` — add `sync_customers` and `sync_invoices` helpers.
* `core/management/commands/sync_quickbooks.py` — call customer and invoice sync.
* `core/engines/__init__.py` — export `run_connectwise_reconciliation` and `generate_connectwise_feed`.
* `core/engines/bank_feed.py` — no change, but confirm import paths remain clean.
* `core/views.py` — add `connectwise_reconciliation_view`, `generate_connectwise_feed_view`.
* `core/urls.py` — add `/dashboard/connectwise/reconcile/` and `/dashboard/connectwise/generate/`.
* `core/templates/core/dashboard_content.html` — add Client Reconciliation section.
* `core/templates/core/connectwise_section.html` — new partial for the section.
* `core/tests/test_views.py` — add dashboard action tests.
* `core/tests/test_management.py` — add command tests.
* `docs/TODO.md` — add ConnectWise integration section.
* `docs/CURRENT_TASK.md` — reflect active work.
* `docs/CHANGELOG.md` — summarize new integration.

## Migration notes

Because the app is pre-production with a squashed initial migration, update `core/migrations/0001_initial.py` directly to include all new models. After editing, verify:

```bash
docker compose exec web python manage.py makemigrations --check --dry-run
```

## Test plan

### Model tests

* Creating `QBCustomer`, `ConnectWiseCompany`, `ClientMapping`, and activity rows with correct defaults.
* `ClientMapping` unique constraints prevent duplicate mappings.

### QBO invoice sync tests

* `sync_quickbooks` creates `QBCustomer` and `Invoice` rows from mocked QBO data.
* Invoice sync is idempotent on `(company, qb_invoice_id)`.

### Synthetic feed tests

* `generate_connectwise_feed` creates the expected number of `TimeEntry`, `ExpenseEntry`, `ProductEntry` rows for each scenario.
* `--force` overwrites existing rows for the month.
* `--seed` produces reproducible output.
* `missing_mapping` scenario creates `ConnectWiseCompany` rows without `ClientMapping`.

### Reconciliation engine tests

* `hourly_leakage` scenario creates a `CONNECTWISE_UNBILLED` flag.
* `flat_fee_margin_erosion` scenario creates a `CONNECTWISE_MARGIN` flag.
* `flat_fee_profitable` scenario creates no margin flag.
* `missing_mapping` scenario creates a `CONNECTWISE_MISSING_MAPPING` flag.
* Re-running reconciliation is idempotent (replaces prior ConnectWise flags).
* Cost-to-serve uses `ConnectWiseWorkRole.burden_rate` when available, global default otherwise.

### View tests

* Dashboard renders the Client Reconciliation section.
* Running reconciliation via dashboard creates flags and returns a notice.
* Generating the test feed via dashboard creates activity rows.

### End-to-end smoke test

1. Run `sync_quickbooks` with mocked QBO invoices and customers.
2. Run `generate_connectwise_feed` for a scenario.
3. Run `run_connectwise_reconciliation`.
4. Open dashboard and confirm flags appear with correct math.

## UI/UX changes

In `core/templates/core/dashboard_content.html`:

1. After the bank balances section, add:

```html
<section id="connectwise-section" aria-label="ConnectWise reconciliation">
    {% include "core/connectwise_section.html" %}
</section>
```

2. `connectwise_section.html` contains:
   * Heading: "Client Reconciliation (ConnectWise)"
   * Action forms: "Run Reconciliation", "Generate Test Feed"
   * Summary metrics
   * Open ConnectWise flags table

3. Keep the existing "Generate Bank Feed" button in its current location.

## Risks and open decisions

| Risk | Mitigation |
|---|---|
| Editing squashed migration for many new tables could drift from models. | Run `makemigrations --check --dry-run` after every model change. |
| QBO customer names won't match ConnectWise names. | Manual `ClientMapping`; synthetic scenarios pair names deliberately. |
| Same-month timing causes false positives for real data. | Documented as MVP limitation; future plan can add lag-aware windows. |
| Invoice-total approach loses line-level detail. | Ingest `InvoiceLine` for future use; flag reasons include per-client totals only. |
| Flat-fee MRR may not be static month-to-month. | `ClientMapping.flat_fee_amount` can be updated manually; future plan can pull from QBO recurring transactions. |
| Burden rates are sensitive. | Use a config table with override; keep global default visible in settings. |

## Future work (out of scope)

* Live ConnectWise REST API integration (`core/connectwise/` package, OAuth/token refresh).
* Fuzzy matching helper for `ClientMapping` creation.
* CSV import for ConnectWise time/expense/product activity.
* Lag-aware reconciliation (e.g. compare January time against January + February invoices).
* Per-client and per-agreement margin thresholds.
* Mapping UI modal in the dashboard.
* Drill-down page per flag showing ticket-level details.

## Commit plan

1. `feat(models): add QBO customer, ConnectWise master, invoice, and activity models`
   * All model changes and migration update; no logic yet.
2. `feat(quickbooks): sync QBO customers and invoices into new models`
   * `sync_customers`, `sync_invoices`, command wiring, tests.
3. `feat(engines): add synthetic ConnectWise feed generator with scenarios`
   * `core/engines/connectwise_feed.py`, command, fixtures, tests.
4. `feat(engines): add ConnectWise-to-QBO reconciliation engine`
   * `core/engines/connectwise_reconciliation.py`, command, flag creation, tests.
5. `feat(views): add ConnectWise dashboard section and actions`
   * Views, URLs, templates, view tests.
6. `docs: update TODO, CURRENT_TASK, and CHANGELOG`

## Verification

* `docker compose exec web python manage.py makemigrations --check --dry-run` reports no changes.
* `docker compose exec web python manage.py test -v 2` passes with new tests.
* Smoke test via dashboard:
  1. Sync mocked QBO (customers + invoices).
  2. Generate ConnectWise test feed.
  3. Run ConnectWise reconciliation.
  4. Confirm flags, totals, and section render correctly.