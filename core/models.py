"""Core data models for the Monthly Close Assistant (Prompt 2 — Postgres Schema).

The schema captures the two sides of a reconciliation (QuickBooks-sourced
``Transaction`` vs. bank-feed ``BankTransaction``), the ``Flag`` records raised by
the analysis engine, and the agent-drafted ``CloseSummary`` for human review.
"""
from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models


class SourceType(models.TextChoices):
    """The QuickBooks record type a Transaction was normalized from."""

    PURCHASE = "Purchase", "Purchase"
    DEPOSIT = "Deposit", "Deposit"
    JOURNAL_ENTRY = "JournalEntry", "Journal Entry"


class Transaction(models.Model):
    """A QuickBooks-sourced transaction, normalized into the internal schema.

    Pulled from Purchase, Deposit, and JournalEntry records during sync.
    ``qb_transaction_id`` is the natural key used for idempotent sync (skip-existing).
    """

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
        unique=True,
        db_index=True,
        help_text="QuickBooks transaction id; natural key for idempotent sync.",
    )
    source_type = models.CharField(
        max_length=20, choices=SourceType.choices, help_text="QuickBooks record type."
    )

    class Meta:
        ordering = ["-date", "vendor"]

    def __str__(self) -> str:
        return f"{self.date} {self.vendor} {self.amount} ({self.source_type})"


class BankTransaction(models.Model):
    """The bank-feed side of a transaction, derived from QuickBooks data.

    Mirrors the ``Transaction`` shape and carries an optional link to the GL
    ``Transaction`` it was matched to during reconciliation (nullable because a bank
    entry may have no GL match).
    """

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
    """

    flag_type = models.CharField(max_length=20, choices=FlagType.choices)
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
    reason = models.TextField(help_text="Human-readable explanation of the issue.")
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


class CloseSummaryStatus(models.TextChoices):
    """Review state of an agent-drafted close summary."""

    DRAFT = "draft", "Draft"
    REVIEWED = "reviewed", "Reviewed"


class CloseSummary(models.Model):
    """An agent-generated monthly close draft awaiting human review.

    The agent only ever produces draft text; a human marks it reviewed (with notes).
    One summary per month (``month`` is unique).
    """

    month = models.CharField(
        max_length=7,
        unique=True,
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

    def __str__(self) -> str:
        return f"Close summary {self.month} ({self.status})"