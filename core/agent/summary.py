"""Agent-drafted monthly close summary (Prompt 10).

Builds a plain-language close summary from:

* Open ``Flag`` records for the month (reconciliation + anomaly).
* Category totals for the month.
* Category totals for the prior month, for month-over-month context.

The agent is implemented as a single-node LangGraph graph whose node calls a
configurable LLM provider. Supported providers:

* ``anthropic`` (default) — uses LangChain-Anthropic / Claude models.
* ``openai`` — uses any OpenAI-compatible API, such as Ollama Cloud.

If no provider is configured or the API key is absent, the node falls back to a
deterministic, human-readable summary so local development and tests do not
require live API access.
"""
from __future__ import annotations

import calendar
import datetime as dt
import logging
from decimal import Decimal
from typing import Any, Optional, TypedDict

from decouple import config
from django.db import transaction
from django.db.models import Q, Sum

from core.models import (
    CloseSummary,
    CloseSummaryStatus,
    Flag,
    FlagStatus,
    Transaction,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a precise accounting assistant drafting a monthly close summary for a "
    "finance reviewer. Summarize the open flags, month-over-month category changes, "
    "and overall spend. Keep the tone professional, concise, and factual. Do not "
    "invent data not present in the inputs."
)


class SummaryState(TypedDict):
    month: str
    inputs: dict
    summary_text: str


def _month_bounds(month: str) -> tuple[dt.date, dt.date]:
    year, mon = int(month[:4]), int(month[5:7])
    first = dt.date(year, mon, 1)
    last = dt.date(year, mon, calendar.monthrange(year, mon)[1])
    return first, last


def _prior_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    if mon == 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def _category_totals(month: str, realm_id: Optional[str] = None) -> dict[str, Decimal]:
    """Return {category: total_amount} for ``month`` (empty categories excluded)."""
    first, last = _month_bounds(month)
    qs = Transaction.objects.filter(date__range=(first, last))
    if realm_id:
        qs = qs.filter(realm_id=realm_id)
    qs = (
        qs.exclude(category="")
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    return {row["category"]: row["total"] for row in qs}


def _prior_category_totals(month: str, realm_id: Optional[str] = None) -> dict[str, Decimal]:
    prev = _prior_month(month)
    return _category_totals(prev, realm_id=realm_id)


def _serialize_flag(flag: Flag) -> dict[str, Any]:
    return {
        "type": flag.flag_type,
        "severity": flag.severity,
        "reason": flag.reason,
        "transaction_id": flag.transaction_id,
        "bank_transaction_id": flag.bank_transaction_id,
    }


def gather_inputs(month: str, realm_id: Optional[str] = None) -> dict[str, Any]:
    """Collect the inputs the agent needs to draft a close summary."""
    first, last = _month_bounds(month)
    txns = Transaction.objects.filter(date__range=(first, last))
    if realm_id:
        txns = txns.filter(realm_id=realm_id)
    total_spend = txns.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    open_flags = Flag.objects.filter(
        status=FlagStatus.OPEN
    ).filter(
        Q(transaction__date__range=(first, last))
        | Q(bank_transaction__date__range=(first, last))
    )
    if realm_id:
        open_flags = open_flags.filter(realm_id=realm_id)
    open_flags = open_flags.select_related("transaction", "bank_transaction")

    prior_txns = Transaction.objects.filter(date__range=_month_bounds(_prior_month(month)))
    if realm_id:
        prior_txns = prior_txns.filter(realm_id=realm_id)
    prior_total = prior_txns.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    return {
        "month": month,
        "realm_id": realm_id or "",
        "total_spend": total_spend,
        "prior_total_spend": prior_total,
        "category_totals": _category_totals(month, realm_id=realm_id),
        "prior_category_totals": _prior_category_totals(month, realm_id=realm_id),
        "open_flags": [_serialize_flag(f) for f in open_flags],
    }


def build_prompt(inputs: dict[str, Any]) -> str:
    """Render the inputs as a prompt for the LLM (or the deterministic fallback)."""
    lines = [
        f"Close month: {inputs['month']}",
        f"Total spend: ${inputs['total_spend']} (prior month: ${inputs['prior_total_spend']})",
        "",
        "Category totals this month:",
    ]
    for category, total in inputs["category_totals"].items():
        prior = inputs["prior_category_totals"].get(category, Decimal("0"))
        change = total - prior
        lines.append(f"  - {category}: ${total} (prior: ${prior}, change: ${change})")

    lines.extend(["", f"Open flags ({len(inputs['open_flags'])}):"])
    if inputs["open_flags"]:
        for flag in inputs["open_flags"]:
            lines.append(
                f"  - [{flag['severity']} {flag['type']}] {flag['reason']}"
            )
    else:
        lines.append("  - No open flags for this month.")

    lines.extend([
        "",
        "Draft a concise monthly close summary based on the above.",
    ])
    return "\n".join(lines)


def _deterministic_summary(inputs: dict[str, Any]) -> str:
    """Generate a readable summary without calling an LLM.

    Used when ``ANTHROPIC_API_KEY`` is not configured.
    """
    lines = [
        f"Monthly Close Summary — {inputs['month']}",
        "",
        f"Total spend: ${inputs['total_spend']} (prior month: ${inputs['prior_total_spend']}).",
        "",
        "Category spend:",
    ]
    if inputs["category_totals"]:
        for category, total in inputs["category_totals"].items():
            prior = inputs["prior_category_totals"].get(category, Decimal("0"))
            lines.append(f"  - {category}: ${total} (prior: ${prior}).")
    else:
        lines.append("  - No categorized transactions.")

    lines.extend(["", f"Open flags: {len(inputs['open_flags'])}"])
    if inputs["open_flags"]:
        for flag in inputs["open_flags"]:
            lines.append(f"  - {flag['severity'].title()} {flag['type']} flag: {flag['reason']}")
    else:
        lines.append("  - None.")

    lines.append("")
    lines.append("Status: Draft — awaiting reviewer approval.")
    return "\n".join(lines)


def _get_summary_provider() -> str:
    """Return the configured close-summary provider (``anthropic`` or ``openai``)."""
    provider = config("CLOSE_SUMMARY_PROVIDER", default="anthropic").strip().lower()
    if provider not in ("anthropic", "openai"):
        logger.warning("Unknown CLOSE_SUMMARY_PROVIDER %r; using anthropic.", provider)
        return "anthropic"
    return provider


def _call_llm(prompt: str, llm: Optional[Any] = None) -> str:
    """Invoke the configured LLM, or fall back to the deterministic summary."""
    if llm is not None:
        return llm.invoke(prompt).content

    provider = _get_summary_provider()
    model_name = config("CLOSE_SUMMARY_MODEL", default="claude-sonnet-4-6")

    if provider == "openai":
        return _call_openai_llm(prompt, model_name)

    return _call_anthropic_llm(prompt, model_name)


def _call_anthropic_llm(prompt: str, model_name: str) -> str | None:
    """Call an Anthropic model via LangChain-Anthropic."""
    api_key = config("ANTHROPIC_API_KEY", default="")
    if not api_key:
        logger.info("ANTHROPIC_API_KEY is not configured; using deterministic close summary.")
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
    """Call an OpenAI-compatible model (e.g. Ollama Cloud) via LangChain-OpenAI."""
    api_key = config("OPENAI_API_KEY", default="")
    if not api_key:
        logger.info("OPENAI_API_KEY is not configured; using deterministic close summary.")
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


def _draft_node(state: SummaryState) -> SummaryState:
    """LangGraph node: build prompt, call LLM/fallback, write summary to state."""
    prompt = build_prompt(state["inputs"])
    summary_text = _call_llm(prompt, llm=state["inputs"].get("_llm"))
    if summary_text is None:
        summary_text = _deterministic_summary(state["inputs"])
    state["summary_text"] = summary_text
    return state


def _build_graph() -> Any:
    """Compile the single-node close-summary LangGraph."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:  # pragma: no cover
        logger.warning("LangGraph not installed: %s. Agent graph unavailable.", exc)
        return None

    builder = StateGraph(SummaryState)
    builder.add_node("draft", _draft_node)
    builder.add_edge(START, "draft")
    builder.add_edge("draft", END)
    return builder.compile()


_GRAPH = _build_graph()


def draft_close_summary(
    month: str, realm_id: Optional[str] = None, llm: Optional[Any] = None
) -> CloseSummary:
    """Draft a close summary for ``realm_id``/``month`` and save it as a ``CloseSummary`` draft.

    ``llm`` is an optional prebuilt LangChain runnable (or any object with an
    ``invoke(prompt)`` method returning an object with a ``.content`` string).
    When omitted, the function reads ``ANTHROPIC_API_KEY`` from the environment
    and builds a Claude-backed chain; if the key is absent, it falls back to a
    deterministic summary.
    """
    inputs = gather_inputs(month, realm_id=realm_id)
    if llm is not None:
        inputs["_llm"] = llm

    if _GRAPH is None:
        # LangGraph not installed: use the deterministic path directly.
        summary_text = _deterministic_summary(inputs)
    else:
        result = _GRAPH.invoke({"month": month, "inputs": inputs, "summary_text": ""})
        summary_text = result["summary_text"]

    with transaction.atomic():
        summary, _ = CloseSummary.objects.update_or_create(
            realm_id=realm_id or "",
            month=month,
            defaults={
                "summary_text": summary_text,
                "status": CloseSummaryStatus.DRAFT,
            },
        )

    logger.info(
        "draft_close_summary(%s, %s): drafted summary (%s chars)",
        month,
        realm_id,
        len(summary_text),
    )
    return summary
