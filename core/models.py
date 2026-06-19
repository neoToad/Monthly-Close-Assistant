"""Core data models for the Monthly Close Assistant (Prompt 2 — Postgres Schema).

The schema captures the two sides of a reconciliation (QuickBooks-sourced
``Transaction`` vs. bank-feed ``BankTransaction``), the ``Flag`` records raised by
the analysis engine, and the agent-drafted ``CloseSummary`` for human review.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class SourceType(models.TextChoices):
    """The QuickBooks record type a Transaction was normalized from."""

    PURCHASE = "Purchase", "Purchase"
    DEPOSIT = "Deposit", "Deposit"
    JOURNAL_ENTRY = "JournalEntry", "Journal Entry"
    BILL = "Bill", "Bill"
    BILL_PAYMENT = "BillPayment", "Bill Payment"
    VENDOR_CREDIT = "VendorCredit", "Vendor Credit"


class QBAccount(models.Model):
    """QuickBooks chart-of-accounts row for a connected realm.

    Stored as master data (not a transaction) so the close workflow can validate
    GL account strings, map account types, and drive account-level checks.
    """

    company = models.ForeignKey(
        "QuickBooksCompany",
        on_delete=models.CASCADE,
        related_name="accounts",
        help_text="QuickBooks company this account belongs to.",
    )
    realm_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="QuickBooks company/realm id this account belongs to.",
    )
    account_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="QuickBooks account id (natural key scoped by realm).",
    )
    name = models.CharField(max_length=200, help_text="Account name as shown in QBO.")
    account_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="QuickBooks account type (e.g. Bank, Expense, Liability).",
    )
    account_sub_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="QuickBooks account sub-type.",
    )
    active = models.BooleanField(default=True, help_text="Whether QBO marks the account active.")

    class Meta:
        ordering = ["name"]
        unique_together = [["company", "account_id"]]
        verbose_name = "QuickBooks account"
        verbose_name_plural = "QuickBooks accounts"

    def __str__(self) -> str:
        return f"{self.name} ({self.account_type or 'Unknown'})"


class BankStatementBalance(models.Model):
    """The ending balance on a bank statement for a cash account in a month.

    This is the control side of a balance-level reconciliation. In production the
    balance comes from a statement upload or manual entry; in sandbox it can be
    auto-seeded from QuickBooks. The assistant compares this ending balance to the
    sum of GL activity hitting the same account name and raises a
    ``BALANCE_RECONCILIATION`` flag when they differ.
    """

    class Source(models.TextChoices):
        """How the balance value entered the system."""

        QB_API = "qb_api", "QuickBooks API"
        MANUAL = "manual", "Manual entry"
        CSV_UPLOAD = "csv_upload", "CSV upload"
        BANK_FEED = "bank_feed", "Bank feed"

    company = models.ForeignKey(
        "QuickBooksCompany",
        on_delete=models.CASCADE,
        related_name="bank_statement_balances",
        help_text="QuickBooks company this balance belongs to.",
    )
    realm_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="QuickBooks company/realm id this balance belongs to.",
    )
    qb_account_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="QuickBooks account id (natural key scoped by realm).",
    )
    account_name = models.CharField(
        max_length=200,
        help_text="Account name as shown in QuickBooks; used to match GL transactions.",
    )
    month = models.CharField(
        max_length=7,
        validators=[RegexValidator(r"^\d{4}-\d{2}$", "Month must be in YYYY-MM format.")],
        help_text="The close month in YYYY-MM format.",
    )
    ending_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Ending balance shown on the bank statement for the account and month.",
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
        help_text="How this balance value was provided.",
    )
    statement_date = models.DateField(
        blank=True,
        null=True,
        help_text="Date the statement balance is as-of (usually the last day of the month).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month", "account_name"]
        unique_together = [["company", "qb_account_id", "month"]]
        verbose_name = "bank statement balance"
        verbose_name_plural = "bank statement balances"

    def __str__(self) -> str:
        return f"{self.account_name} — {self.month}: {self.ending_balance}"


class Transaction(models.Model):
    """A QuickBooks-sourced transaction, normalized into the internal schema.

    Pulled from Purchase, Deposit, and JournalEntry records during sync.
    ``qb_transaction_id`` is unique only within a QuickBooks realm, so idempotency
    is keyed on ``(company, qb_transaction_id)``.
    """

    company = models.ForeignKey(
        "QuickBooksCompany",
        on_delete=models.CASCADE,
        related_name="transactions",
        help_text="QuickBooks company this transaction belongs to.",
    )
    realm_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="QuickBooks company/realm id this transaction belongs to.",
    )
    date = models.DateField(help_text="Transaction date as recorded in QuickBooks.")
    vendor = models.CharField(max_length=200, help_text="Payee / vendor name.")
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Transaction amount in USD."
    )
    category = models.CharField(
        max_length=100, blank=True, default="", help_text="Expense/income category."
    )
    gl_account = models.CharField(
        max_length=100, blank=True, default="", help_text="General ledger account."
    )
    qb_transaction_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="QuickBooks transaction id; natural key for idempotent sync (scoped by company).",
    )
    source_type = models.CharField(
        max_length=20, choices=SourceType.choices, help_text="QuickBooks record type."
    )

    class Meta:
        ordering = ["-date", "vendor"]
        unique_together = [["company", "qb_transaction_id"]]

    def __str__(self) -> str:
        return f"{self.date} {self.vendor} {self.amount} ({self.source_type})"


class BankTransaction(models.Model):
    """The bank-feed side of a transaction, derived from QuickBooks data.

    Mirrors the ``Transaction`` shape and carries an optional link to the GL
    ``Transaction`` it was matched to during reconciliation (nullable because a bank
    entry may have no GL match).
    """

    company = models.ForeignKey(
        "QuickBooksCompany",
        on_delete=models.CASCADE,
        related_name="bank_transactions",
        help_text="QuickBooks company this bank row belongs to.",
    )
    realm_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="QuickBooks company/realm id this bank row belongs to.",
    )
    date = models.DateField(help_text="Date the transaction posted to the bank.")
    vendor = models.CharField(max_length=200, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=100, blank=True, default="")
    gl_account = models.CharField(max_length=100, blank=True, default="")
    qb_transaction_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Originating QuickBooks id, if derived from a GL transaction.",
    )
    source_type = models.CharField(
        max_length=20, choices=SourceType.choices, blank=True, default=""
    )
    matched_transaction_id = models.ForeignKey(
        Transaction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bank_transactions",
        help_text="The GL Transaction this bank entry was matched to, if any.",
    )

    class Meta:
        ordering = ["-date", "vendor"]

    def __str__(self) -> str:
        return f"Bank {self.date} {self.vendor} {self.amount}"


class FlagType(models.TextChoices):
    """Kind of issue a Flag records."""

    RECONCILIATION = "reconciliation", "Reconciliation"
    ANOMALY = "anomaly", "Anomaly"
    BALANCE_RECONCILIATION = "balance_reconciliation", "Balance Reconciliation"


class Severity(models.TextChoices):
    """Rough severity for triage on the review dashboard."""

    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class FlagStatus(models.TextChoices):
    """Lifecycle of a Flag on the human review dashboard."""

    OPEN = "open", "Open"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Flag(models.Model):
    """A reconciliation mismatch or anomaly raised for human review.

    Relates to either a ``Transaction`` or a ``BankTransaction`` (whichever side the
    issue is on); both are nullable because a flag may point at only one side.
    ``realm_id`` is denormalized from the linked transaction/bank row for fast filtering.
    """

    company = models.ForeignKey(
        "QuickBooksCompany",
        on_delete=models.CASCADE,
        related_name="flags",
        help_text="QuickBooks company this flag belongs to.",
    )
    realm_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="QuickBooks company/realm id this flag belongs to.",
    )
    flag_type = models.CharField(max_length=25, choices=FlagType.choices)
    transaction = models.ForeignKey(
        Transaction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="flags",
        help_text="The GL transaction this flag concerns, if any.",
    )
    bank_transaction = models.ForeignKey(
        BankTransaction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="flags",
        help_text="The bank transaction this flag concerns, if any.",
    )
    bank_statement_balance = models.ForeignKey(
        BankStatementBalance,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="flags",
        help_text="For balance-reconciliation flags, the statement balance that triggered the flag.",
    )
    reason = models.TextField(help_text="Human-readable explanation of the issue.")
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Optional audit notes, e.g. what QuickBooks objects were created.",
    )
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.LOW
    )
    status = models.CharField(
        max_length=10, choices=FlagStatus.choices, default=FlagStatus.OPEN
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        reason_preview = (self.reason or "")[:50]
        return f"[{self.severity}] {self.flag_type}: {reason_preview}"

    def display_vendor(self) -> str:
        """Return the vendor name from whichever side the flag points to."""
        if self.transaction_id is not None and self.transaction.vendor:
            return self.transaction.vendor
        if self.bank_transaction_id is not None and self.bank_transaction.vendor:
            return self.bank_transaction.vendor
        return "—"

    def display_amount(self) -> "Decimal | None":
        """Return the amount from whichever side the flag points to."""
        if self.transaction_id is not None:
            return self.transaction.amount
        if self.bank_transaction_id is not None:
            return self.bank_transaction.amount
        return None


class ReconciliationStatus(models.TextChoices):
    """Lifecycle of an account-level reconciliation workflow."""

    UNRECONCILED = "unreconciled", "Unreconciled"
    IN_PROGRESS = "in_progress", "In Progress"
    RECONCILED = "reconciled", "Reconciled"
    REVIEWED = "reviewed", "Reviewed"


class AccountReconciliationState(models.Model):
    """Tracks progress per (company, qb_account_id, month) for the AI-assisted
    reconciliation workflow.

    Stores the control statement balance, posted GL total, difference, current
    status, and cached/applied suggestions so the workflow is resumable and
    auditable.
    """

    company = models.ForeignKey(
        "QuickBooksCompany",
        on_delete=models.CASCADE,
        related_name="reconciliation_states",
        help_text="QuickBooks company this reconciliation state belongs to.",
    )
    realm_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="QuickBooks company/realm id this state belongs to.",
    )
    qb_account_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="QuickBooks account id (natural key scoped by realm).",
    )
    month = models.CharField(
        max_length=7,
        validators=[RegexValidator(r"^\d{4}-\d{2}$", "Month must be in YYYY-MM format.")],
        help_text="The close month in YYYY-MM format.",
    )
    statement_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Stored statement balance for the account and month.",
    )
    posted_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Posted GL total at the time suggestions were generated.",
    )
    difference = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Statement balance minus posted GL total.",
    )
    status = models.CharField(
        max_length=15,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.UNRECONCILED,
        help_text="Current reconciliation status.",
    )
    reviewer_notes = models.TextField(
        blank=True,
        default="",
        help_text="Optional reviewer notes for the reconciliation.",
    )
    last_suggestions = models.JSONField(
        blank=True,
        default=dict,
        help_text="Cache of the latest LLM/deterministic suggestions.",
    )
    applied_suggestions = models.JSONField(
        blank=True,
        default=list,
        help_text="Suggestion ids that have already been applied to QuickBooks.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month", "qb_account_id"]
        unique_together = [["company", "qb_account_id", "month"]]
        verbose_name = "account reconciliation state"
        verbose_name_plural = "account reconciliation states"

    def __str__(self) -> str:
        return f"{self.qb_account_id} — {self.month}: {self.status}"


class CloseSummaryStatus(models.TextChoices):
    """Review state of an agent-drafted close summary."""

    DRAFT = "draft", "Draft"
    REVIEWED = "reviewed", "Reviewed"


class CloseSummary(models.Model):
    """An agent-generated monthly close draft awaiting human review.

    The agent only ever produces draft text; a human marks it reviewed (with notes).
    One summary per company per month (``(company, month)`` is unique).
    """

    company = models.ForeignKey(
        "QuickBooksCompany",
        on_delete=models.CASCADE,
        related_name="close_summaries",
        help_text="QuickBooks company this summary belongs to.",
    )
    realm_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="QuickBooks company/realm id this summary belongs to.",
    )
    month = models.CharField(
        max_length=7,
        validators=[RegexValidator(r"^\d{4}-\d{2}$", "Month must be in YYYY-MM format.")],
        help_text="The close month in YYYY-MM format.",
    )
    summary_text = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=10,
        choices=CloseSummaryStatus.choices,
        default=CloseSummaryStatus.DRAFT,
    )
    reviewer_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month"]
        verbose_name_plural = "close summaries"
        unique_together = [["company", "month"]]

    def __str__(self) -> str:
        return f"Close summary {self.month} ({self.status})"


class QBToken(models.Model):
    """Encrypted QuickBooks OAuth tokens, one row per company.

    Added in Prompt 3 so the OAuth callback and the ``sync_quickbooks`` command can
    persist access/refresh tokens at rest and reload them later. The token values
    are stored Fernet-encrypted (see ``core.quickbooks.tokens``); the model exposes
    plaintext accessors only through ``get_access_token`` / ``get_refresh_token``.
    """

    company = models.ForeignKey(
        "QuickBooksCompany",
        on_delete=models.CASCADE,
        related_name="token",
        help_text="QuickBooks company these tokens belong to.",
    )
    realm_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="QuickBooks company/realm id (the sandbox realm for this build).",
    )
    access_token_encrypted = models.TextField(help_text="Fernet-encrypted access token.")
    refresh_token_encrypted = models.TextField(help_text="Fernet-encrypted refresh token.")
    access_token_expires_at = models.DateTimeField(
        null=True, blank=True, help_text="When the access token expires."
    )
    refresh_token_expires_at = models.DateTimeField(
        null=True, blank=True, help_text="When the (long-lived) refresh token expires."
    )
    last_refreshed = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"QBToken realm={self.realm_id} (refreshed {self.last_refreshed})"

    def get_access_token(self) -> str:
        from core.quickbooks.tokens import decrypt_value

        return decrypt_value(self.access_token_encrypted)

    def get_refresh_token(self) -> str:
        from core.quickbooks.tokens import decrypt_value

        return decrypt_value(self.refresh_token_encrypted)

    def is_access_token_expired(self, buffer_minutes: Optional[int] = None) -> bool:
        """Return True when the access token is expired or within the refresh buffer.

        ``buffer_minutes`` defaults to ``QB_TOKEN_REFRESH_BUFFER_MINUTES`` from
        Django settings (Prompt 4). A token expiring inside that window is treated as
        expired so it can be refreshed before the QuickBooks API rejects it mid-sync.
        """
        if self.access_token_expires_at is None:
            return True

        if buffer_minutes is None:
            from django.conf import settings

            buffer_minutes = getattr(settings, "QB_TOKEN_REFRESH_BUFFER_MINUTES", 15)

        buffer = dt.timedelta(minutes=int(buffer_minutes))
        return self.access_token_expires_at <= timezone.now() + buffer



class QuickBooksCompanyManager(models.Manager):
    """Manager helpers for ``QuickBooksCompany``.

    ``for_realm`` returns the company row for a realm id, creating it on demand with
    an optional display name. This is the single place where realm-scoped code links
    rows to a canonical ``QuickBooksCompany`` record.
    """

    def for_realm(self, realm_id: str, name: str = "") -> "QuickBooksCompany":
        company, _ = self.get_or_create(
            realm_id=realm_id,
            defaults={"name": name or "", "is_connected": True},
        )
        if name and not company.name:
            company.name = name
            company.save(update_fields=["name"])
        return company


class QuickBooksCompany(models.Model):
    """Lightweight metadata about a connected QuickBooks realm.

    Created automatically when tokens are stored. The ``name`` is optional and can
    be edited later; the UI falls back to ``realm_id`` when ``name`` is blank.
    """

    objects = QuickBooksCompanyManager()

    realm_id = models.CharField(
        max_length=50,
        primary_key=True,
        help_text="QuickBooks company/realm id.",
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Human-readable company name (optional).",
    )
    is_connected = models.BooleanField(
        default=True,
        help_text="Whether this realm currently has stored tokens.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "QuickBooks companies"

    def __str__(self) -> str:
        return self.name or self.realm_id
