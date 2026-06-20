"""Django admin registration for the core models (Prompt 2 — Postgres Schema).

All models are registered with list displays, filters, and search fields tuned
for an internal reviewer scanning the close data.
"""
from __future__ import annotations

from django.contrib import admin

from core.models import (
    AccountReconciliationState,
    BankStatementBalance,
    BankTransaction,
    ClientMapping,
    CloseSummary,
    ConnectWiseCompany,
    ConnectWiseWorkRole,
    ExpenseEntry,
    Flag,
    Invoice,
    InvoiceLine,
    ProductEntry,
    QBAccount,
    QBCustomer,
    QBToken,
    QuickBooksCompany,
    TimeEntry,
    Transaction,
)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "vendor", "amount", "category", "source_type", "qb_transaction_id")
    list_filter = ("source_type", "date", "category")
    search_fields = ("vendor", "qb_transaction_id", "category", "gl_account")
    date_hierarchy = "date"


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "vendor", "amount", "matched_transaction_id")
    list_filter = ("date",)
    search_fields = ("vendor", "qb_transaction_id")
    date_hierarchy = "date"


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin):
    list_display = ("flag_type", "severity", "status", "transaction", "bank_transaction", "created_at")
    list_filter = ("flag_type", "severity", "status", "created_at")
    search_fields = ("reason",)


@admin.register(CloseSummary)
class CloseSummaryAdmin(admin.ModelAdmin):
    list_display = ("month", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("month", "summary_text", "reviewer_notes")


@admin.register(QBToken)
class QBTokenAdmin(admin.ModelAdmin):
    """Read-only-ish view of the stored QuickBooks OAuth tokens.

    The encrypted token fields are deliberately excluded from ``list_display`` and
    ``fields`` so a reviewer never sees raw (or ciphertext) secrets in the admin.
    """
    list_display = ("realm_id", "last_refreshed", "access_token_expires_at", "updated_at")
    list_filter = ("updated_at",)
    search_fields = ("realm_id",)
    fields = ("realm_id", "last_refreshed", "access_token_expires_at",
              "refresh_token_expires_at", "created_at", "updated_at")
    readonly_fields = ("realm_id", "last_refreshed", "access_token_expires_at",
                        "refresh_token_expires_at", "created_at", "updated_at")


@admin.register(BankStatementBalance)
class BankStatementBalanceAdmin(admin.ModelAdmin):
    list_display = ("account_name", "month", "ending_balance", "source", "realm_id")
    list_filter = ("source", "month")
    search_fields = ("account_name", "qb_account_id", "realm_id")


@admin.register(QBAccount)
class QBAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "account_type", "account_sub_type", "active", "realm_id")
    list_filter = ("account_type", "active")
    search_fields = ("name", "account_id", "realm_id")


@admin.register(QuickBooksCompany)
class QuickBooksCompanyAdmin(admin.ModelAdmin):
    list_display = ("realm_id", "name", "is_connected", "created_at")
    list_filter = ("is_connected", "created_at")
    search_fields = ("realm_id", "name")
    readonly_fields = ("realm_id", "created_at")


@admin.register(AccountReconciliationState)
class AccountReconciliationStateAdmin(admin.ModelAdmin):
    list_display = ("company", "qb_account_id", "month", "status", "difference", "updated_at")
    list_filter = ("status", "month")
    search_fields = ("qb_account_id", "realm_id")
    readonly_fields = ("updated_at",)


@admin.register(QBCustomer)
class QBCustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "customer_id", "active", "realm_id")
    list_filter = ("active",)
    search_fields = ("name", "customer_id", "realm_id")


@admin.register(ConnectWiseCompany)
class ConnectWiseCompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "connectwise_id", "realm_id")
    search_fields = ("name", "connectwise_id", "realm_id")


@admin.register(ClientMapping)
class ClientMappingAdmin(admin.ModelAdmin):
    list_display = ("connectwise_company", "qbo_customer", "billing_model", "flat_fee_amount", "realm_id")
    list_filter = ("billing_model",)
    search_fields = ("connectwise_company__name", "qbo_customer__name", "realm_id")


@admin.register(ConnectWiseWorkRole)
class ConnectWiseWorkRoleAdmin(admin.ModelAdmin):
    list_display = ("role_name", "burden_rate", "realm_id")
    search_fields = ("role_name", "realm_id")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "invoice_date", "total_amount", "realm_id")
    list_filter = ("invoice_date",)
    search_fields = ("customer_name", "qb_invoice_id", "realm_id")
    date_hierarchy = "invoice_date"


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ("invoice", "line_number", "amount", "service_item")
    search_fields = ("description", "service_item")


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("connectwise_company", "date", "technician", "hours", "work_role", "realm_id")
    list_filter = ("date", "work_role")
    search_fields = ("connectwise_company__name", "technician", "ticket_number")
    date_hierarchy = "date"


@admin.register(ExpenseEntry)
class ExpenseEntryAdmin(admin.ModelAdmin):
    list_display = ("connectwise_company", "date", "amount", "description", "realm_id")
    list_filter = ("date",)
    search_fields = ("connectwise_company__name", "description")
    date_hierarchy = "date"


@admin.register(ProductEntry)
class ProductEntryAdmin(admin.ModelAdmin):
    list_display = ("connectwise_company", "date", "amount", "description", "realm_id")
    list_filter = ("date",)
    search_fields = ("connectwise_company__name", "description")
    date_hierarchy = "date"
