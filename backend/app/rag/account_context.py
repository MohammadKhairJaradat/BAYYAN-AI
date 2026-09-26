"""User-scoped account context for chat answers."""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.fingerprint import input_fingerprint
from app.models import DeductionCategory, MaritalStatus
from app.models.database import (
    AdvisorReportSnapshot,
    Deduction,
    Document,
    IncomeSource,
    TaxProfile,
)
from app.models.schemas import ProfileUpdateOption, ProfileUpdateSuggestion
from app.tax_engine import TaxInput, calculate_tax
from app.services.tax_snapshot import build_tax_input, load_tax_snapshot


DOCUMENT_SUMMARY_LIMIT = 8
CONTEXT_CHAR_LIMIT = 9000

_ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_THOUSAND_SUFFIXES = {
    "k",
    "thousand",
    "thousands",
    "\u0627\u0644\u0641",
    "\u0623\u0644\u0641",
    "\u0622\u0644\u0627\u0641",
    "\u0627\u0644\u0627\u0641",
}
_THOUSAND_SUFFIX_PATTERN = (
    r"k|thousand|thousands|\u0627\u0644\u0641|\u0623\u0644\u0641"
    r"|\u0622\u0644\u0627\u0641|\u0627\u0644\u0627\u0641"
)
_AMOUNT_TOKEN_PATTERN = (
    rf"([+-]?\d[\d,]*(?:\.\d+)?)\s*({_THOUSAND_SUFFIX_PATTERN})?"
)

_ACCOUNT_QUERY_RE = re.compile(
    r"\b(my|account|profile|salary|income|withheld|deduction|deductions"
    r"|exemption|exemptions|personal exemption|family exemption"
    r"|document|documents|uploaded|receipt|receipts|advisor|report|plan|risk"
    r"|owe|refund|tax due|tax liability|what if|how much tax|missing deductions)\b"
    r"|دخلي|راتبي|ملفي|حسابي|خصوماتي|مستنداتي|وثائقي|وصل|وصولات"
    r"|إعفائي|اعفائي|إعفاءاتي|اعفاءاتي|رفعت|حملت|تقرير|المستشار|الخطة|المخاطر|ضريبتي|استرداد|كم أدفع|كم ادفع",
    re.IGNORECASE,
)

_ACCOUNT_CALC_RE = re.compile(
    r"\b(how much tax|tax due|tax liability|owe|net tax|refund|calculate my"
    r"|what if|how about|what about|if i|if i'm|if i am)\b"
    r"|ضريبتي|كم أدفع|كم ادفع|المستحق|استرداد|لو|ماذا لو|إذا|اذا",
    re.IGNORECASE,
)

_INCOME_OVERRIDE_RE = re.compile(
    r"(?:salary|income|gross income|annual salary|دخلي|دخل|راتبي|راتب)"
    rf"[^+\-\d]{{0,40}}{_AMOUNT_TOKEN_PATTERN}",
    re.IGNORECASE,
)
_CURRENCY_OVERRIDE_RE = re.compile(
    rf"{_AMOUNT_TOKEN_PATTERN}\s*(?:JOD|JD|دينار)",
    re.IGNORECASE,
)
_DEPENDENTS_RE = re.compile(
    r"(\d+)\s*(?:dependent|dependents|child|children|kid|kids"
    r"|معال|معالين|أبناء|ابناء|أولاد|اولاد|أطفال|اطفال)",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})\b")

_SAFE_EXTRACTED_KEYS = {
    "amount",
    "date",
    "category",
    "document_type",
    "confidence",
    "vendor",
    "currency",
    "tax_year",
    "income",
    "gross_income",
    "salary",
    "tax_withheld",
    "employer",
    "employer_name",
    "period",
    "description",
    "error",
    "extractor_backend",
}


@dataclass(slots=True)
class AccountChatContext:
    context: str | None
    sources: list[dict[str, Any]]
    tax_inputs: TaxInput | None
    selected_tax_year: int | None
    profile_id: uuid.UUID | None
    # Always populated (when a profile exists) so the understanding layer can route,
    # merge prior-turn figures, and detect contradictions — independent of whether the
    # turn is "account-related" enough to inject the full context string above.
    base_inputs: TaxInput | None = None
    snapshot: dict[str, Any] | None = None  # LLM-safe stored values (no internal ids)
    profile: TaxProfile | None = None
    income_sources: list[IncomeSource] = field(default_factory=list)
    deductions: list[Deduction] = field(default_factory=list)


def _normalize_digits(text: str) -> str:
    return text.translate(_ARABIC_INDIC_DIGITS)


def requested_tax_year(question: str) -> int | None:
    normalized = _normalize_digits(question or "")
    match = _YEAR_RE.search(normalized)
    return int(match.group(1)) if match else None


def is_account_related_question(question: str) -> bool:
    return bool(_ACCOUNT_QUERY_RE.search(_normalize_digits(question or "")))


def should_calculate_from_account(question: str) -> bool:
    return bool(_ACCOUNT_CALC_RE.search(_normalize_digits(question or "")))


def _clip(value: Any, limit: int = 180) -> Any:
    if not isinstance(value, str):
        return value
    if len(value) <= limit:
        return value
    return value[: limit - 12].rstrip() + " [truncated]"


def _compact_json(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
    if len(text) <= CONTEXT_CHAR_LIMIT:
        return text
    return text[: CONTEXT_CHAR_LIMIT - 20].rstrip() + "\n[truncated]"


def _safe_extracted_data(data: dict | None) -> dict[str, Any] | None:
    if not data:
        return None
    out: dict[str, Any] = {}
    for key, value in data.items():
        normalized = str(key)
        if normalized not in _SAFE_EXTRACTED_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[normalized] = _clip(value)
    return out or None


def _count_by(rows: list[Any], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = getattr(row, attr, None) or "unknown"
        out[value] = out.get(value, 0) + 1
    return out


def _tax_profile_payload(profile: TaxProfile) -> dict[str, Any]:
    return {
        "id": str(profile.id),
        "tax_year": profile.tax_year,
        "marital_status": profile.marital_status,
        "num_dependents": profile.num_dependents,
        "filing_status": profile.filing_status,
        "residency_status": profile.residency_status,
        "claims_dependents_exemption": profile.claims_dependents_exemption,
        "claim_spouse_expense_exemption": profile.claim_spouse_expense_exemption,
        "disability_exemption_count": profile.disability_exemption_count,
    }


def _income_payload(rows: list[IncomeSource]) -> list[dict[str, Any]]:
    return [
        {
            "type": row.type,
            "amount": float(row.amount),
            "tax_withheld": float(row.tax_withheld or 0),
            "employer_name": row.employer_name,
            "description": _clip(row.description),
        }
        for row in rows
    ]


def _deduction_payload(rows: list[Deduction]) -> list[dict[str, Any]]:
    return [
        {
            "category": row.category,
            "amount": float(row.amount),
            "date": row.date.isoformat() if row.date else None,
            "description": _clip(row.description),
            "document_id": str(row.document_id) if row.document_id else None,
        }
        for row in rows
    ]


def _documents_payload(rows: list[Document]) -> dict[str, Any]:
    recent = sorted(
        rows,
        key=lambda row: row.upload_date.timestamp() if row.upload_date else 0,
        reverse=True,
    )[:DOCUMENT_SUMMARY_LIMIT]
    return {
        "total": len(rows),
        "by_type": _count_by(rows, "document_type"),
        "by_status": _count_by(rows, "processing_status"),
        "recent": [
            {
                "id": str(row.id),
                "filename": row.original_filename,
                "document_type": row.document_type,
                "processing_status": row.processing_status,
                "upload_date": row.upload_date.isoformat() if row.upload_date else None,
                "extracted_summary": _safe_extracted_data(row.extracted_data),
            }
            for row in recent
        ],
    }


def _coerce_marital(value: str | None) -> MaritalStatus:
    try:
        return MaritalStatus(value or "single")
    except ValueError:
        return MaritalStatus.single


def _tax_inputs_from_rows(
    profile: TaxProfile,
    income_rows: list[IncomeSource],
    deduction_rows: list[Deduction],
) -> TaxInput:
    return build_tax_input(profile, income_rows, deduction_rows)


def _amount_from_question(question: str) -> float | None:
    normalized = _normalize_digits(question or "")
    match = _INCOME_OVERRIDE_RE.search(normalized)
    if not match:
        match = _CURRENCY_OVERRIDE_RE.search(normalized)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").strip().lower()
    if suffix in _THOUSAND_SUFFIXES:
        amount *= 1000
    return amount


def _apply_question_overrides(base: TaxInput, question: str) -> TaxInput:
    normalized = _normalize_digits(question or "")
    result = copy.deepcopy(base)

    amount = _amount_from_question(normalized)
    if amount is not None:
        result.gross_income = amount

    if re.search(r"\b(single|unmarried)\b|أعزب|اعزب|عزباء", normalized, re.IGNORECASE):
        result.marital_status = MaritalStatus.single
    elif re.search(r"\b(married|spouse|wife|husband)\b|متزوج|متزوجة|زوج|زوجة", normalized, re.IGNORECASE):
        result.marital_status = MaritalStatus.married

    dep_match = _DEPENDENTS_RE.search(normalized)
    if dep_match:
        result.num_dependents = int(dep_match.group(1))

    return result


def merge_tax_inputs(base: TaxInput | None, stated: dict[str, Any]) -> TaxInput:
    """Apply chat-stated slots over the stored base inputs (or defaults).

    ``stated`` is the cumulative set of facts the user asserted across the whole
    conversation (from the understanding layer), so prior-turn figures survive into
    follow-ups. Implements the platform-wide marital convention (mirrors
    ``create_tax_profile``): stating *married* turns on the spouse expense allowance
    and the family/dependents exemption — the lever that actually changes the tax —
    unless the user explicitly set those flags. Stating *single* clears the spouse
    allowance.
    """
    result = copy.deepcopy(base) if base is not None else TaxInput(gross_income=0.0)

    if "gross_income" in stated:
        result.gross_income = float(stated["gross_income"])
    if "tax_withheld" in stated:
        result.tax_withheld = float(stated["tax_withheld"])
    if "num_dependents" in stated:
        result.num_dependents = int(stated["num_dependents"])
    if "disability_exemption_count" in stated:
        result.disability_exemption_count = int(stated["disability_exemption_count"])

    marital = stated.get("marital_status")
    if marital in {"single", "married"}:
        result.marital_status = MaritalStatus(marital)
        if marital == "married":
            if "claim_spouse_expense_exemption" not in stated:
                result.claim_spouse_expense_exemption = True
            if "claims_dependents_exemption" not in stated:
                result.claims_dependents_exemption = True
        elif "claim_spouse_expense_exemption" not in stated:
            result.claim_spouse_expense_exemption = False

    if "claims_dependents_exemption" in stated:
        result.claims_dependents_exemption = bool(stated["claims_dependents_exemption"])
    if "claim_spouse_expense_exemption" in stated:
        result.claim_spouse_expense_exemption = bool(stated["claim_spouse_expense_exemption"])

    for item in stated.get("deductions") or []:
        try:
            category = DeductionCategory(item["category"])
        except (KeyError, ValueError, TypeError):
            continue
        merged = dict(result.deductions)
        merged[category] = float(item["amount"])
        result.deductions = merged

    return result


def _account_snapshot(
    profile: TaxProfile,
    income_rows: list[IncomeSource],
    deduction_rows: list[Deduction],
) -> dict[str, Any]:
    """Compact, LLM-safe view of the stored profile (no internal ids)."""
    return {
        "tax_year": profile.tax_year,
        "gross_income": sum(float(row.amount) for row in income_rows),
        "marital_status": profile.marital_status,
        "num_dependents": profile.num_dependents,
        "claims_dependents_exemption": bool(profile.claims_dependents_exemption),
        "claim_spouse_expense_exemption": bool(profile.claim_spouse_expense_exemption),
        "disability_exemption_count": profile.disability_exemption_count,
        "income_sources": [
            {
                "type": row.type,
                "amount": float(row.amount),
                "employer_name": row.employer_name,
            }
            for row in income_rows
        ],
        "deductions": [
            {"category": row.category, "amount": float(row.amount)}
            for row in deduction_rows
        ],
    }


def build_profile_updates(
    stated: dict[str, Any],
    profile: TaxProfile | None,
    income_rows: list[IncomeSource],
    deduction_rows: list[Deduction],
) -> list[ProfileUpdateSuggestion]:
    """Diff chat-stated facts against the stored account → confirm-and-write offers.

    Field-general: any stated value that contradicts the stored snapshot becomes a
    suggestion. Profile scalars are 1:1; income maps to one row / create / choose;
    deductions update an existing category or create one.
    """
    out: list[ProfileUpdateSuggestion] = []
    if profile is None or not stated:
        return out

    # ── Income (multi-row → needs a mapping rule) ──────────────────────────────
    if "gross_income" in stated:
        new_total = float(stated["gross_income"])
        stored_total = sum(float(row.amount) for row in income_rows)
        if abs(new_total - stored_total) > 0.5:
            if len(income_rows) == 1:
                row = income_rows[0]
                out.append(
                    ProfileUpdateSuggestion(
                        entity="income_source",
                        field="amount",
                        action="update",
                        entity_id=row.id,
                        current_value=float(row.amount),
                        new_value=new_total,
                        label_ar="تحديث الدخل في ملفك",
                        label_en="Update income in your profile",
                    )
                )
            elif not income_rows:
                out.append(
                    ProfileUpdateSuggestion(
                        entity="income_source",
                        field="amount",
                        action="create",
                        current_value=0.0,
                        new_value=new_total,
                        label_ar="إضافة مصدر دخل لملفك",
                        label_en="Add income source to your profile",
                    )
                )
            else:
                out.append(
                    ProfileUpdateSuggestion(
                        entity="income_source",
                        field="amount",
                        action="choose",
                        current_value=stored_total,
                        new_value=new_total,
                        label_ar="عندك أكثر من مصدر دخل — أي مصدر تريد تحديثه؟",
                        label_en="You have multiple income sources — which one to update?",
                        options=[
                            ProfileUpdateOption(
                                entity_id=row.id,
                                label=row.employer_name or row.type or "Income",
                                current_value=float(row.amount),
                            )
                            for row in income_rows
                        ],
                    )
                )

    # ── Profile scalars (clean 1:1) ────────────────────────────────────────────
    if "marital_status" in stated and (profile.marital_status or "single") != stated["marital_status"]:
        out.append(
            ProfileUpdateSuggestion(
                entity="tax_profile",
                field="marital_status",
                action="update",
                entity_id=profile.id,
                current_value=profile.marital_status,
                new_value=stated["marital_status"],
                label_ar="تحديث الحالة الاجتماعية",
                label_en="Update marital status",
            )
        )
    if "num_dependents" in stated and int(profile.num_dependents or 0) != int(stated["num_dependents"]):
        out.append(
            ProfileUpdateSuggestion(
                entity="tax_profile",
                field="num_dependents",
                action="update",
                entity_id=profile.id,
                current_value=int(profile.num_dependents or 0),
                new_value=int(stated["num_dependents"]),
                label_ar="تحديث عدد المعالين",
                label_en="Update number of dependents",
            )
        )
    if "disability_exemption_count" in stated and int(profile.disability_exemption_count or 0) != int(
        stated["disability_exemption_count"]
    ):
        out.append(
            ProfileUpdateSuggestion(
                entity="tax_profile",
                field="disability_exemption_count",
                action="update",
                entity_id=profile.id,
                current_value=int(profile.disability_exemption_count or 0),
                new_value=int(stated["disability_exemption_count"]),
                label_ar="تحديث عدد إعفاءات الإعاقة",
                label_en="Update disability exemption count",
            )
        )

    # ── Employer name (only unambiguous with a single income row) ──────────────
    if "employer_name" in stated and len(income_rows) == 1:
        row = income_rows[0]
        if (row.employer_name or "") != stated["employer_name"]:
            out.append(
                ProfileUpdateSuggestion(
                    entity="income_source",
                    field="employer_name",
                    action="update",
                    entity_id=row.id,
                    current_value=row.employer_name,
                    new_value=stated["employer_name"],
                    label_ar="تحديث اسم جهة العمل",
                    label_en="Update employer name",
                )
            )

    # ── Deductions (update matching category or create) ────────────────────────
    for item in stated.get("deductions") or []:
        try:
            category = DeductionCategory(item["category"])
        except (KeyError, ValueError, TypeError):
            continue
        amount = float(item["amount"])
        match = next((row for row in deduction_rows if row.category == category.value), None)
        if match is None:
            out.append(
                ProfileUpdateSuggestion(
                    entity="deduction",
                    field="amount",
                    action="create",
                    category=category.value,
                    current_value=0.0,
                    new_value=amount,
                    label_ar=f"إضافة خصم ({category.value})",
                    label_en=f"Add {category.value} deduction",
                )
            )
        elif abs(float(match.amount) - amount) > 0.5:
            out.append(
                ProfileUpdateSuggestion(
                    entity="deduction",
                    field="amount",
                    action="update",
                    entity_id=match.id,
                    category=category.value,
                    current_value=float(match.amount),
                    new_value=amount,
                    label_ar=f"تحديث خصم ({category.value})",
                    label_en=f"Update {category.value} deduction",
                )
            )

    return out


def _serialize_breakdown(breakdown) -> dict[str, Any]:
    return {
        "gross_income": breakdown.gross_income,
        "personal_exemption": breakdown.personal_exemption,
        "family_exemption": breakdown.family_exemption,
        "expense_exemption": breakdown.expense_exemption,
        "disability_exemption": breakdown.disability_exemption,
        "total_exemptions": breakdown.total_exemptions,
        "deductions_allowed": {k.value: v for k, v in breakdown.deductions_allowed.items()},
        "deductions_disallowed": {
            k.value: v for k, v in breakdown.deductions_disallowed.items()
        },
        "total_deductions": breakdown.total_deductions,
        "taxable_income": breakdown.taxable_income,
        "bracket_breakdown": breakdown.bracket_breakdown,
        "national_contribution": breakdown.national_contribution,
        "tax_liability": breakdown.tax_liability,
        "total_tax_withheld": breakdown.total_tax_withheld,
        "net_tax_due": breakdown.net_tax_due,
        "refund_due": breakdown.refund_due,
        "effective_rate": breakdown.effective_rate,
        "marginal_rate": breakdown.marginal_rate,
    }


async def _selected_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
    question: str,
    *,
    current_year: int,
) -> tuple[TaxProfile | None, int | None, list[int]]:
    explicit_year = requested_tax_year(question)
    result = await db.execute(
        select(TaxProfile)
        .where(TaxProfile.user_id == user_id)
        .order_by(TaxProfile.tax_year.desc())
    )
    profiles = list(result.scalars().all())
    years = [profile.tax_year for profile in profiles]
    target_year = explicit_year or current_year
    for profile in profiles:
        if profile.tax_year == target_year:
            return profile, target_year, years
    return None, target_year, years


async def build_account_chat_context(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    question: str,
    current_year: int | None = None,
) -> AccountChatContext:
    """Build a bounded, authenticated account packet for chat.

    The stored profile rows, ``base_inputs`` and a compact ``snapshot`` are ALWAYS
    computed (when a profile exists) so the understanding layer can route, carry
    prior-turn figures, and detect contradictions. The heavier injected ``context``
    string + ``sources`` + legacy override ``tax_inputs`` are produced only when the
    turn is account-related, preserving prior behavior for greetings/small talk.
    """

    target_year = current_year or dt.date.today().year
    profile, selected_year, available_years = await _selected_profile(
        db, user_id, question, current_year=target_year
    )

    # Always load the stored profile rows for the router/contradiction layer.
    income_rows: list[IncomeSource] = []
    deduction_rows: list[Deduction] = []
    base_inputs: TaxInput | None = None
    account_snapshot: dict[str, Any] | None = None
    if profile is not None:
        tax_snapshot = await load_tax_snapshot(
            db, user_id=user_id, profile_id=profile.id, include_exact=False,
        )
        assert tax_snapshot is not None
        income_rows = tax_snapshot.income_rows
        deduction_rows = tax_snapshot.deduction_rows
        base_inputs = tax_snapshot.legacy_input
        account_snapshot = _account_snapshot(profile, income_rows, deduction_rows)

    def _context() -> AccountChatContext:
        return AccountChatContext(
            context=context,
            sources=sources,
            tax_inputs=tax_inputs,
            selected_tax_year=selected_year,
            profile_id=profile.id if profile else None,
            base_inputs=base_inputs,
            snapshot=account_snapshot,
            profile=profile,
            income_sources=income_rows,
            deductions=deduction_rows,
        )

    # Non-account turns: hand back router data only (no injected context/sources).
    if not is_account_related_question(question):
        context = None
        sources = []
        tax_inputs = None
        return _context()

    document_rows = (
        await db.execute(select(Document).where(Document.user_id == user_id))
    ).scalars().all()
    documents_summary = _documents_payload(list(document_rows))

    payload: dict[str, Any] = {
        "scope": "authenticated_user_account",
        "selected_tax_year": selected_year,
        "available_tax_years": available_years,
        "documents_summary": documents_summary,
    }
    sources = []
    tax_inputs = None

    if profile is None:
        payload["tax_profile"] = None
        payload["note"] = f"No tax profile was found for tax year {selected_year}."
    else:
        baseline = calculate_tax(base_inputs)
        tax_inputs = (
            _apply_question_overrides(base_inputs, question)
            if should_calculate_from_account(question)
            else None
        )

        payload.update(
            {
                "tax_profile": _tax_profile_payload(profile),
                "income_sources": _income_payload(income_rows),
                "deductions": _deduction_payload(deduction_rows),
                "latest_deterministic_tax_calculation": _serialize_breakdown(baseline),
            }
        )

        sources.extend(
            [
                {
                    "citation": f"Tax profile {profile.tax_year}",
                    "kind": "account_profile",
                    "label": "Current account tax profile",
                    "tax_year": profile.tax_year,
                },
                {
                    "citation": f"Deterministic tax calculation {profile.tax_year}",
                    "kind": "account_calculation",
                    "label": "Deterministic tax calculation",
                    "tax_year": profile.tax_year,
                },
            ]
        )

        advisor_snapshot = (
            await db.execute(
                select(AdvisorReportSnapshot).where(
                    AdvisorReportSnapshot.tax_profile_id == profile.id,
                    AdvisorReportSnapshot.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if advisor_snapshot is not None:
            current_fingerprint = await input_fingerprint(profile, db)
            stale = advisor_snapshot.input_fingerprint != current_fingerprint
            payload["latest_advisor_report"] = {
                "status": "stale" if stale else "fresh",
                "updated_at": advisor_snapshot.updated_at.isoformat()
                if advisor_snapshot.updated_at
                else None,
                "lang": advisor_snapshot.lang,
                "report": advisor_snapshot.report,
            }
            sources.append(
                {
                    "citation": "Latest advisor report",
                    "kind": "advisor_report",
                    "label": "Latest advisor report",
                    "stale": stale,
                    "updated_at": advisor_snapshot.updated_at.isoformat()
                    if advisor_snapshot.updated_at
                    else None,
                    "tax_year": profile.tax_year,
                }
            )

    if document_rows:
        sources.append(
            {
                "citation": "Uploaded document summary",
                "kind": "account_documents",
                "label": "Uploaded document summary",
                "tax_year": selected_year,
            }
        )

    context = (
        "Authenticated account context. Use only for this signed-in user. "
        "Do not reveal hidden IDs unless the user asks for diagnostics. "
        "Raw document files are not included; document data below is metadata "
        "and extracted summaries only.\n"
        f"{_compact_json(payload)}"
    )

    return _context()
