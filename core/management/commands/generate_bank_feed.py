"""``generate_bank_feed`` management command (Prompt 6).

(Testing/simulator only.) Reads ``Transaction`` records for a given month and creates
a deliberately imperfect set of ``BankTransaction`` records for reconciliation
testing. Discrepancy rates are configurable via command-line options.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.engines import generate_bank_feed
from core.quickbooks import tokens as qb_tokens


class Command(BaseCommand):
    help = (
        "(Testing/simulator only) Generate synthetic BankTransaction records for a month, "
        "introducing configurable discrepancies for reconciliation testing."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            help="QuickBooks realm ID (company) to scope the bank feed to.",
        )
        parser.add_argument(
            "--drop-rate",
            type=float,
            default=0.05,
            help="Fraction of GL transactions to drop from the bank feed (default 0.05).",
        )
        parser.add_argument(
            "--dup-rate",
            type=float,
            default=0.03,
            help="Fraction of remaining transactions to duplicate (default 0.03).",
        )
        parser.add_argument(
            "--amount-shift-rate",
            type=float,
            default=0.04,
            help="Fraction of rows to nudge by a small amount delta (default 0.04).",
        )
        parser.add_argument(
            "--date-shift-rate",
            type=float,
            default=0.05,
            help="Fraction of rows to shift by 1-2 days (default 0.05).",
        )
        parser.add_argument(
            "--extra-rate",
            type=float,
            default=0.03,
            help="Fraction of extra bank-only transactions to add (default 0.03).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing BankTransaction records for the month.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Random seed for reproducible discrepancy generation.",
        )
        parser.add_argument(
            "--cash-only",
            action="store_true",
            help=(
                "Only use transactions that represent actual cash movement "
                "(Purchase, Deposit, BillPayment, and cash-like JournalEntry lines). "
                "Ignored when --scenario=independent."
            ),
        )
        parser.add_argument(
            "--scenario",
            default="derived",
            choices=["derived", "independent"],
            help=(
                "Scenario that drives the bank feed source. 'derived' mutates GL "
                "transactions; 'independent' uses a fixture of realistic bank rows."
            ),
        )
        parser.add_argument(
            "--scenario-file",
            help="Path to a custom JSON scenario fixture (used with --scenario independent).",
        )

    def _resolve_realm_id(self, realm_id: str | None) -> str:
        if realm_id:
            return realm_id
        token = qb_tokens.get_active_token()
        if token:
            return token.realm_id
        raise CommandError(
            "--realm-id is required when no QuickBooks token is stored."
        )

    def handle(self, *args, **options) -> None:
        month = options["month"]
        realm_id = self._resolve_realm_id(options.get("realm_id"))

        try:
            result = generate_bank_feed(
                month=month,
                realm_id=realm_id,
                drop_rate=options["drop_rate"],
                dup_rate=options["dup_rate"],
                amount_shift_rate=options["amount_shift_rate"],
                date_shift_rate=options["date_shift_rate"],
                extra_rate=options["extra_rate"],
                force=options["force"],
                seed=options["seed"],
                cash_only=options["cash_only"],
                scenario=options["scenario"],
                scenario_file=options["scenario_file"],
            )
        except ValueError as exc:
            raise CommandError(str(exc))

        if result.get("message"):
            self.stdout.write(self.style.WARNING(result["message"]))
            return

        scenario_label = options["scenario"]
        self.stdout.write(self.style.SUCCESS(
            f"Bank feed generated for {month} (scenario={scenario_label}): "
            f"created={result['created']} bank rows"
        ))
        self.stdout.write("Discrepancy summary:")
        self.stdout.write(f"  Dropped:          {result['dropped']}")
        self.stdout.write(f"  Duplicated:       {result['duplicated']}")
        self.stdout.write(f"  Amount shifts:    {result['amount_shifts']}")
        self.stdout.write(f"  Date shifts:      {result['date_shifts']}")
        self.stdout.write(f"  Extra bank-only:  {result['extras']}")
