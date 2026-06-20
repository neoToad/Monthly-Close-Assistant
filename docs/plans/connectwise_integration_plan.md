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