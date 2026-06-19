"""``run_reconciliation`` management command (Prompt 7).

Reconciles GL ``Transaction`` records against ``BankTransaction`` records for a month
and creates ``Flag`` records for mismatches or one-sided entries. Also runs anomaly
detection when implemented (Prompt 8).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from core.anomaly.rules import run_anomaly_detection
from core.reconciliation.engine import run_reconciliation


class Command(BaseCommand):
    help = (
        "Reconcile Transaction and BankTransaction records for a month, creating "
        "reconciliation Flag records, then run anomaly detection on the month's "
        "Transaction data."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            help="QuickBooks realm ID (company) to scope reconciliation to.",
        )

    def handle(self, *args, **options) -> None:
        month = options["month"]
        realm_id = options.get("realm_id")
        rec_result = run_reconciliation(month, realm_id=realm_id)

        if rec_result.get("message"):
            self.stdout.write(self.style.WARNING(rec_result["message"]))
            # Still run anomaly detection when there are no bank rows but there are
            # GL transactions; the message only fires when both sides are empty.

        self.stdout.write(self.style.SUCCESS(
            f"Reconciliation complete for {month}: "
            f"{rec_result.get('flags_created', 0)} flag(s) created"
        ))
        self.stdout.write(
            f"  Matched bank rows:    {rec_result.get('matched_bank_rows', 0)}"
        )
        self.stdout.write(
            f"  Unmatched bank rows:  {rec_result.get('unmatched_bank_rows', 0)}"
        )
        self.stdout.write(
            f"  Unmatched GL rows:    {rec_result.get('unmatched_gl_rows', 0)}"
        )
        self.stdout.write(
            f"  Accounts checked:     {rec_result.get('accounts_checked', 0)}"
        )
        self.stdout.write(
            f"  Balance flags:        {rec_result.get('balance_flags_created', 0)}"
        )

        anomaly_result = run_anomaly_detection(month, realm_id=realm_id)
        if anomaly_result.get("message"):
            self.stdout.write(self.style.WARNING(anomaly_result["message"]))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Anomaly detection complete for {month}: "
                f"{anomaly_result['anomaly_flags_created']} flag(s) created"
            ))
