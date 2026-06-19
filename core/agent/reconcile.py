"""Account-level reconciliation suggestion engine.

Specialized agent that proposes explainable, human-reviewable adjusting entries
to close the gap between a stored bank statement balance and the posted GL total
for a single QuickBooks cash account.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Optional

from decouple import config
from django.db import transaction
from django.db.models import Count

from core.common.constants import (
    AMOUNT_TOLERANCE,
    BANK_FEES_THRESHOLD,
    DEFAULT_BANK_FEES_ACCOUNT,
    DEFAULT_EXPENSE_ACCOUNT,
    DEFAULT_INCOME_ACCOUNT,
)
from core.common.dates import month_bounds, prior_month
from core.models import (
    AccountReconciliationState,
    BankStatementBalance,
    BankTransaction,
    QuickBooksCompany,
    ReconciliationStatus,
    Transaction,
)
from core.quickbooks import client as qb_client
from core.reconciliation.engine import compute_posted_total

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a precise accounting assistant. Given a bank statement balance, the "
    "posted GL total, and unmatched bank/GL items, propose specific adjusting "
    "entries that a reviewer can confirm before writing to QuickBooks. "
    "Return ONLY a JSON object matching the requested schema. Do not invent data "
    "not present in the inputs."
)


def _account_name_for_qb_account_id(realm_id: str, qb_account_id: str) -> str:
    """Return the stored account name for a QB account id, or the id itself."""
    from core.models import QBAccount

    try:
        return QBAccount.objects.get(realm_id=realm_id, account_id=qb_account_id).name
    except QBAccount.DoesNotExist:
        return qb_account_id


def _serialize_bank_row(row: BankTransaction) -> dict[str, Any]:
    return {
        "id": row.id,
        "date": row.date.isoformat(),
        "vendor": row.vendor,
        "amount": str(row.amount),
        "category": row.category,
        "gl_account": row.gl_account,
        "qb_transaction_id": row.qb_transaction_id or "",
        "matched": row.matched_transaction_id is not None,
    }


def _serialize_txn_row(row: Transaction) -> dict[str, Any]:
    return {
        "id": row.id,
        "date": row.date.isoformat(),
        "vendor": row.vendor,
        "amount": str(row.amount),
        "category": row.category,
        "gl_account": row.gl_account,
        "qb_transaction_id": row.qb_transaction_id,
        "source_type": row.source_type,
    }


def gather_account_inputs(
    month: str,
    realm_id: str,
    qb_account_id: str,
    qb_api_client: Optional[Any] = None,
) -> dict[str, Any]:
    """Collect the inputs the reconciliation agent needs for one account/month."""
    first, last = month_bounds(month)
    realm_id = realm_id or ""
    company = QuickBooksCompany.objects.for_realm(realm_id) if realm_id else None

    balance: BankStatementBalance | None = None
    if company is not None:
        try:
            balance = BankStatementBalance.objects.get(
                company=company,
                qb_account_id=qb_account_id,
                month=month,
            )
        except BankStatementBalance.DoesNotExist:
            balance = None

    account_name = balance.account_name if balance else _account_name_for_qb_account_id(realm_id, qb_account_id)

    posted_total = compute_posted_total(month, account_name, realm_id=realm_id)

    bank_rows = BankTransaction.objects.filter(
        realm_id=realm_id,
        date__range=(first, last),
    ).select_related("matched_transaction_id")
    unmatched_bank = [r for r in bank_rows if r.matched_transaction_id is None]

    # Use a Count annotation to find GL rows with no linked bank transactions in one query.
    unmatched_gl = list(
        Transaction.objects.filter(
            realm_id=realm_id,
            date__range=(first, last),
        )
        .annotate(bank_count=Count("bank_transactions"))
        .filter(bank_count=0)
    )

    # Simple matched-but-different detection: same vendor + within date tolerance,
    # but amount differs beyond tolerance.
    matched_diffs: list[dict[str, Any]] = []
    for bank in bank_rows:
        if bank.matched_transaction_id is None:
            continue
        txn = bank.matched_transaction_id
        if abs(bank.amount - txn.amount) > AMOUNT_TOLERANCE:
            matched_diffs.append({
                "bank": _serialize_bank_row(bank),
                "gl": _serialize_txn_row(txn),
                "difference": str(bank.amount - txn.amount),
            })

    prior_balance: Decimal | None = None
    if balance is not None:
        prior_qs = BankStatementBalance.objects.filter(
            company=company,
            qb_account_id=qb_account_id,
            month=prior_month(month),
        )
        if prior_qs.exists():
            prior_balance = prior_qs.first().ending_balance

    qb_current_balance: Decimal | None = None
    if qb_api_client is not None:
        try:
            balances = qb_client.fetch_account_current_balances(qb_api_client)
            info = balances.get(qb_account_id)
            if info:
                qb_current_balance = Decimal(str(info.get("balance", 0)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch QB current balance for %s: %s", qb_account_id, exc)

    return {
        "month": month,
        "realm_id": realm_id,
        "qb_account_id": qb_account_id,
        "account_name": account_name,
        "statement_balance": balance.ending_balance if balance else None,
        "posted_total": posted_total,
        "difference": (balance.ending_balance - posted_total) if balance else None,
        "bank_transactions": [_serialize_bank_row(r) for r in bank_rows],
        "unmatched_bank": [_serialize_bank_row(r) for r in unmatched_bank],
        "unmatched_gl": [_serialize_txn_row(txn) for txn in unmatched_gl],
        "matched_differences": matched_diffs,
        "prior_balance": str(prior_balance) if prior_balance is not None else None,
        "qb_current_balance": str(qb_current_balance) if qb_current_balance is not None else None,
    }


def build_account_reconcile_prompt(inputs: dict[str, Any]) -> str:
    """Render agent inputs as a prompt for the LLM or deterministic fallback."""
    lines = [
        f"Close month: {inputs['month']}",
        f"QuickBooks account id: {inputs['qb_account_id']}",
        f"Account name: {inputs['account_name']}",
    ]
    if inputs["statement_balance"] is not None:
        lines.append(f"Bank statement ending balance: ${inputs['statement_balance']}")
    lines.append(f"Posted GL total: ${inputs['posted_total']}")
    if inputs["difference"] is not None:
        lines.append(f"Difference (bank - GL): ${inputs['difference']}")
    if inputs.get("qb_current_balance"):
        lines.append(f"QuickBooks current balance (reference only): ${inputs['qb_current_balance']}")
    if inputs.get("prior_balance"):
        lines.append(f"Prior-month ending balance: ${inputs['prior_balance']}")

    lines.extend(["", f"Unmatched bank rows ({len(inputs['unmatched_bank'])}):"])
    if inputs["unmatched_bank"]:
        for row in inputs["unmatched_bank"]:
            lines.append(
                f"  - {row['date']} {row['vendor']} ${row['amount']}"
            )
    else:
        lines.append("  - None")

    lines.extend(["", f"Unmatched GL rows ({len(inputs['unmatched_gl'])}):"])
    if inputs["unmatched_gl"]:
        for row in inputs["unmatched_gl"]:
            lines.append(
                f"  - {row['date']} {row['vendor']} ${row['amount']} ({row['source_type']})"
            )
    else:
        lines.append("  - None")

    lines.extend(["", f"Matched rows with amount differences ({len(inputs['matched_differences'])}):"])
    if inputs["matched_differences"]:
        for diff in inputs["matched_differences"]:
            lines.append(
                f"  - {diff['bank']['vendor']}: bank ${diff['bank']['amount']} vs GL ${diff['gl']['amount']} "
                f"(diff ${diff['difference']})"
            )
    else:
        lines.append("  - None")

    lines.extend([
        "",
        "Propose adjusting entries that close the difference. Return ONLY JSON in this shape:",
        json.dumps({
            "suggestions": [
                {
                    "id": "sug-1",
                    "type": "purchase",
                    "description": "Bank-only ACH Transfer for $3,000.00 has no GL match",
                    "amount": "3000.00",
                    "date": "2026-06-12",
                    "vendor": "ACH Transfer",
                    "account_id": inputs["qb_account_id"],
                    "confidence": "high",
                    "lines": [
                        {"account_name": inputs["account_name"], "amount": "-3000.00", "posting": "Credit"},
                        {"account_name": "Uncategorized Expense", "amount": "3000.00", "posting": "Debit"},
                    ],
                },
                {
                    "id": "sug-2",
                    "type": "journal_entry",
                    "description": "Residual $53.55 likely bank fees / rounding",
                    "amount": "53.55",
                    "date": "2026-06-30",
                    "confidence": "medium",
                    "lines": [
                        {"account_name": "Bank Fees", "amount": "53.55", "posting": "Debit"},
                        {"account_name": inputs["account_name"], "amount": "-53.55", "posting": "Credit"},
                    ],
                },
            ]
        }, indent=2),
        "",
        "Rules: only create adjusting entries (JournalEntry, Deposit, Purchase). "
        "Never delete or edit existing QB objects. Each suggestion must have a unique id, "
        "a type, a description, an amount string, a date, a confidence (high/medium/low), "
        "and balanced lines with account_name, amount, and posting (Debit/Credit).",
    ])
    return "\n".join(lines)


def _next_suggestion_id(index: int) -> str:
    return f"sug-{index + 1}"


def _deterministic_suggestions(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate suggestions without calling an LLM.

    Covers two cases:
    * Bank-only rows  -> Purchase (money out) or Deposit (money in) suggestions.
    * Residual difference after those -> JournalEntry against a default adjustment account.
    * Unmatched GL rows are described in the prompt but never suggested as writes.

    Accounting math example:
    - ``posted_total`` is the current GL cash-account total for the month.
    - ``statement_balance`` is the bank's ending balance.
    - A bank-only row of +$100 means the bank shows money going out; we suggest a
      Purchase that credits cash $100 and debits an expense account.
    - After covering bank-only rows, ``residual = statement_balance -
      (posted_total + deposits - purchases)``. If the residual is positive, the GL
      total is too high, so we debit an offset account and credit cash. If negative,
      we debit cash and credit the offset account.
    """
    suggestions: list[dict[str, Any]] = []
    account_name = inputs["account_name"]
    statement_balance = Decimal(str(inputs["statement_balance"])) if inputs["statement_balance"] is not None else Decimal("0")
    posted_total = Decimal(str(inputs["posted_total"]))

    # Cover bank-only rows first.
    for index, row in enumerate(inputs["unmatched_bank"], start=0):
        amount = Decimal(str(row["amount"]))
        txn_date = row["date"]
        vendor = row["vendor"] or "Unknown"
        if amount > 0:
            suggestion_type = "purchase"
            offset_account = DEFAULT_EXPENSE_ACCOUNT
            description = f"Bank-only {vendor} for ${amount} has no GL match"
            lines = [
                {"account_name": account_name, "amount": str(-amount), "posting": "Credit"},
                {"account_name": offset_account, "amount": str(amount), "posting": "Debit"},
            ]
        else:
            abs_amount = abs(amount)
            suggestion_type = "deposit"
            offset_account = DEFAULT_INCOME_ACCOUNT
            description = f"Bank-only {vendor} for ${abs_amount} (income) has no GL match"
            lines = [
                {"account_name": account_name, "amount": str(abs_amount), "posting": "Debit"},
                {"account_name": offset_account, "amount": str(-abs_amount), "posting": "Credit"},
            ]
        suggestions.append({
            "id": _next_suggestion_id(index),
            "type": suggestion_type,
            "description": description,
            "amount": str(abs(amount)),
            "date": txn_date,
            "vendor": vendor,
            "account_id": inputs["qb_account_id"],
            "confidence": "medium",
            "lines": lines,
        })

    # Residual after bank-only rows.
    covered = sum((Decimal(str(s["amount"])) for s in suggestions if s["type"] in ("purchase", "deposit")), start=Decimal("0"))
    # The residual is what is still needed to make statement_balance == posted_total + adjustments.
    # For money out, a purchase reduces the GL total (credit cash) by its amount, so new posted_total
    # becomes posted_total - purchase_amount. We need statement_balance == posted_total - covered + residual_entry?
    # Actually we are creating GL entries. The target GL total for the cash account should equal statement_balance.
    # A purchase with credit cash for amount X reduces cash GL total by X.
    # A deposit with debit cash for amount X increases cash GL total by X.
    # So after covering bank-only rows, residual = statement_balance - (posted_total + deposit_covered - purchase_covered).
    purchase_total = sum((Decimal(str(s["amount"])) for s in suggestions if s["type"] == "purchase"), start=Decimal("0"))
    deposit_total = sum((Decimal(str(s["amount"])) for s in suggestions if s["type"] == "deposit"), start=Decimal("0"))
    residual = statement_balance - (posted_total + deposit_total - purchase_total)

    if abs(residual) > AMOUNT_TOLERANCE:
        abs_residual = abs(residual)
        if abs_residual <= BANK_FEES_THRESHOLD:
            offset_account = DEFAULT_BANK_FEES_ACCOUNT
            description = f"Residual ${abs_residual} likely bank fees / rounding"
            confidence = "medium"
        else:
            offset_account = DEFAULT_EXPENSE_ACCOUNT
            description = f"Residual ${abs_residual} unknown difference"
            confidence = "low"

        last_day = month_bounds(inputs["month"])[1]
        if residual > 0:
            # GL total is too high relative to bank; we need to reduce cash (credit) and debit expense.
            lines = [
                {"account_name": offset_account, "amount": str(residual), "posting": "Debit"},
                {"account_name": account_name, "amount": str(-residual), "posting": "Credit"},
            ]
        else:
            # GL total is too low; debit cash, credit income/expense.
            lines = [
                {"account_name": account_name, "amount": str(abs_residual), "posting": "Debit"},
                {"account_name": offset_account, "amount": str(-abs_residual), "posting": "Credit"},
            ]
        suggestions.append({
            "id": _next_suggestion_id(len(suggestions)),
            "type": "journal_entry",
            "description": description,
            "amount": str(abs_residual),
            "date": last_day.isoformat(),
            "confidence": confidence,
            "lines": lines,
        })

    return suggestions


def _clean_suggestion(suggestion: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any] | None:
    """Validate and normalize a single LLM suggestion.

    Drops suggestions that are missing required keys, have an unsupported type, an
    unparseable amount, fewer than two lines, or any line with an invalid posting type
    (only ``Debit`` / ``Credit`` are accepted). Sets sensible defaults for ``vendor``
    and ``account_id`` from the inputs when the LLM omits them.
    """
    required = {"id", "type", "description", "amount", "date", "confidence", "lines"}
    if not required.issubset(set(suggestion.keys())):
        return None
    if suggestion["type"] not in {"journal_entry", "purchase", "deposit"}:
        return None
    try:
        Decimal(str(suggestion["amount"]))
    except Exception:
        return None
    if not isinstance(suggestion["lines"], list) or len(suggestion["lines"]) < 2:
        return None
    for line in suggestion["lines"]:
        if not {"account_name", "amount", "posting"}.issubset(set(line.keys())):
            return None
        if line["posting"] not in {"Debit", "Credit"}:
            return None
    suggestion.setdefault("vendor", inputs["account_name"])
    suggestion.setdefault("account_id", inputs["qb_account_id"])
    return suggestion


def _parse_llm_json(text: str) -> list[dict[str, Any]]:
    """Extract the JSON object from an LLM response and return suggestions list."""
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown code fences.
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    suggestions = data.get("suggestions", [])
    if not isinstance(suggestions, list):
        return []
    return suggestions


def _get_reconcile_provider() -> str:
    provider = config("RECONCILE_PROVIDER", default="anthropic").strip().lower()
    if provider not in ("anthropic", "openai"):
        logger.warning("Unknown RECONCILE_PROVIDER %r; using anthropic.", provider)
        return "anthropic"
    return provider


def _call_llm(prompt: str, llm: Optional[Any] = None) -> str | None:
    """Invoke the configured LLM, or return None to fall back to deterministic suggestions."""
    if llm is not None:
        return llm.invoke(prompt).content

    provider = _get_reconcile_provider()
    model_name = config("RECONCILE_MODEL", default="claude-sonnet-4-6")

    if provider == "openai":
        return _call_openai_llm(prompt, model_name)
    return _call_anthropic_llm(prompt, model_name)


def _call_anthropic_llm(prompt: str, model_name: str) -> str | None:
    api_key = config("ANTHROPIC_API_KEY", default="")
    if not api_key:
        logger.info("ANTHROPIC_API_KEY is not configured; using deterministic reconciliation suggestions.")
        return None
    try:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError as exc:  # pragma: no cover
        logger.warning("Agent dependencies not installed: %s. Using fallback.", exc)
        return None

    chat = ChatAnthropic(model=model_name, api_key=api_key)
    template = ChatPromptTemplate.from_messages(
        [("system", _SYSTEM_PROMPT), ("human", "{prompt}")]
    )
    chain = template | chat
    return chain.invoke({"prompt": prompt}).content


def _call_openai_llm(prompt: str, model_name: str) -> str | None:
    api_key = config("OPENAI_API_KEY", default="")
    if not api_key:
        logger.info("OPENAI_API_KEY is not configured; using deterministic reconciliation suggestions.")
        return None
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover
        logger.warning("OpenAI dependencies not installed: %s. Using fallback.", exc)
        return None

    base_url = config("OPENAI_BASE_URL", default="")
    chat_kwargs: dict[str, Any] = {"model": model_name, "api_key": api_key}
    if base_url:
        chat_kwargs["base_url"] = base_url

    chat = ChatOpenAI(**chat_kwargs)
    template = ChatPromptTemplate.from_messages(
        [("system", _SYSTEM_PROMPT), ("human", "{prompt}")]
    )
    chain = template | chat
    return chain.invoke({"prompt": prompt}).content


def suggest_account_fixes(
    month: str,
    realm_id: str,
    qb_account_id: str,
    qb_api_client: Optional[Any] = None,
    llm: Optional[Any] = None,
) -> dict[str, Any]:
    """Generate adjusting-entry suggestions for a single account/month.

    Falls back to deterministic suggestions when no API key is configured or when
    the LLM returns invalid JSON.
    """
    realm_id = realm_id or ""
    company = QuickBooksCompany.objects.for_realm(realm_id) if realm_id else None
    inputs = gather_account_inputs(
        month, realm_id, qb_account_id, qb_api_client=qb_api_client
    )

    suggestions: list[dict[str, Any]] = []
    if llm is not None:
        prompt = build_account_reconcile_prompt(inputs)
        raw = llm.invoke(prompt).content
        suggestions = [_clean_suggestion(s, inputs) for s in _parse_llm_json(raw)]
        suggestions = [s for s in suggestions if s is not None]

    if not suggestions:
        if llm is None:
            prompt = build_account_reconcile_prompt(inputs)
            raw = _call_llm(prompt)
            if raw is not None:
                suggestions = [_clean_suggestion(s, inputs) for s in _parse_llm_json(raw)]
                suggestions = [s for s in suggestions if s is not None]
        if not suggestions:
            suggestions = _deterministic_suggestions(inputs)

    # Persist state for audit/resumability.
    if company is not None:
        with transaction.atomic():
            defaults = {
                "realm_id": realm_id,
                "statement_balance": inputs["statement_balance"] or Decimal("0"),
                "posted_total": inputs["posted_total"],
                "difference": inputs["difference"] or Decimal("0"),
                "status": ReconciliationStatus.IN_PROGRESS,
                "last_suggestions": {"suggestions": suggestions, "inputs_hash": hash(str(inputs))},
            }
            AccountReconciliationState.objects.update_or_create(
                company=company,
                qb_account_id=qb_account_id,
                month=month,
                defaults=defaults,
            )

    logger.info(
        "suggest_account_fixes(%s, %s, %s): generated %s suggestion(s)",
        month,
        realm_id,
        qb_account_id,
        len(suggestions),
    )

    return {
        "month": month,
        "realm_id": realm_id,
        "qb_account_id": qb_account_id,
        "account_name": inputs["account_name"],
        "statement_balance": inputs["statement_balance"],
        "posted_total": inputs["posted_total"],
        "difference": inputs["difference"],
        "suggestions": suggestions,
    }
