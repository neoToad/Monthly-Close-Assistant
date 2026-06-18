"""``run_reconciliation`` management command (Prompt 7).

Reconciles GL ``Transaction`` records against ``BankTransaction`` records for a month
and creates ``Flag`` records for mismatches or one-sided entries. Also runs anomaly
detection when implemented (Prompt 8).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from core.reconciliation.engine import run_reconciliation


class Command(BaseCommand):
    help = (
        "Reconcile Transaction and BankTransaction records for a month, creating "
        "reconciliation Flag records for mismatches and one-sided entries."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")

    def handle(self, *args, **options) -> None:
        month = options["month"]
        result = run_reconciliation(month)

        if result.get("message"):
            self.stdout.write(self.style.WARNING(result["message"]))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Reconciliation complete for {month}: {result['flags_created']} flag(s) created"
        ))
        self.stdout.write(f"  Matched bank rows:    {result['matched_bank_rows']}")
        self.stdout.write(f"  Unmatched bank rows:  {result['unmatched_bank_rows']}")
        self.stdout.write(f"  Unmatched GL rows:    {result['unmatched_gl_rows']}")
