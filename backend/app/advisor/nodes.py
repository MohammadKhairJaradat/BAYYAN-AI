"""LangGraph node implementations for the advisor pipeline.

Each node is an async function that receives the current AdvisorState plus a
RunnableConfig (which carries the DB session under `configurable["db"]`) and
returns a partial state dict to merge.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor import prompts
from app.advisor.llm import complete_json
from app.advisor.state import AdvisorState
from app.models.database import (
    Deduction,
    Document,
    IncomeSource,
    TaxProfile,
)
from app.rag.retriever import retrieve_with_context
from app.tax_engine import TaxInput, calculate_tax, model_scenarios
from app.services.tax_snapshot import build_tax_input

logger = logging.getLogger(__name__)


def _db_from(config: RunnableConfig) -> AsyncSession:
    return config["configurable"]["db"]


def _append_error(state: AdvisorState, message: str) -> list[str]:
    errors = list(state.get("errors") or [])
    errors.append(message)
    return errors


def _fallback_deduction_findings(state: AdvisorState) -> dict[str, Any]:
    lang = state.get("lang", "ar")
    if lang == "ar":
        narrative = (
            "تعذر قراءة تحليل الخصومات من نموذج المستشار، لذلك سأكمل بحذر "
            "اعتمادا على ملفك الضريبي والحساب الحتمي بدون افتراض خصومات جديدة."
        )
    else:
        narrative = (
            "I could not parse the advisor model's deduction analysis, so I will "
            "continue cautiously from your stored profile and deterministic tax result "
            "without inventing new deductions."
        )
    return {"opportunities": [], "narrative": narrative}


def _fallback_action_plan(state: AdvisorState) -> dict[str, Any]:
    lang = state.get("lang", "ar")
    steps: list[dict[str, Any]] = []

    def add_step(
        priority: int,
        action_en: str,
        description_en: str,
        action_ar: str,
        description_ar: str,
    ) -> None:
        action = action_ar if lang == "ar" else action_en
        if any(step["action"] == action for step in steps):
            return
        steps.append(
            {
                "priority": priority,
                "action": action,
                "description": description_ar if lang == "ar" else description_en,
            }
        )

    income_rows = state.get("income_rows") or []
    deduction_rows = state.get("deduction_rows") or []
    docs_summary = state.get("documents_summary") or {}
    by_type = {
        str(key.value if hasattr(key, "value") else key): value
        for key, value in (docs_summary.get("by_type") or {}).items()
    }
    baseline = state.get("baseline_breakdown") or {}

    has_salary_income = any(row.get("type") == "salary" for row in income_rows)
    if has_salary_income and int(by_type.get("salary_slip", 0) or 0) <= 0:
        add_step(
            1,
            "Upload a salary slip for each salary income source.",
            "Salary income is present, but no salary slip is on file yet.",
            "ارفع قسيمة راتب لكل مصدر دخل من الراتب.",
            "يوجد دخل راتب في الملف، لكن لا توجد قسيمة راتب مرفوعة بعد.",
        )

    manual_categories = sorted(
        {
            str(row.get("category"))
            for row in deduction_rows
            if row.get("category") and not row.get("document_id")
        }
    )
    if manual_categories:
        cats = ", ".join(manual_categories)
        add_step(
            1 if not steps else 2,
            "Attach evidence for manually entered deductions.",
            f"These deduction categories have no linked document yet: {cats}.",
            "اربط مستندا داعما للخصومات المدخلة يدويا.",
            f"هذه الخصومات لا يوجد لها مستند مرتبط بعد: {cats}.",
        )

    disallowed = {
        str(key.value if hasattr(key, "value") else key): float(value or 0)
        for key, value in (baseline.get("deductions_disallowed") or {}).items()
        if float(value or 0) > 0
    }
    if disallowed:
        cats = ", ".join(sorted(disallowed))
        add_step(
            3,
            "Review deductions that the tax engine currently disallowed.",
            f"The deterministic calculation marked these categories as disallowed or above cap: {cats}.",
            "راجع الخصومات التي لم يقبلها محرك الضريبة حاليا.",
            f"الحساب الحتمي وضع هذه الفئات كغير مقبولة أو فوق السقف: {cats}.",
        )

    if (
        float(baseline.get("refund_due") or 0) > 0
        and float(baseline.get("total_tax_withheld") or 0) > 0
    ):
        add_step(
            4,
            "Keep withholding proof ready before requesting a refund.",
            "The calculation shows a possible refund, so the withholding evidence should be easy to verify.",
            "احتفظ بإثبات الاقتطاع قبل طلب الاسترداد.",
            "الحساب يظهر احتمال وجود استرداد، لذلك يجب أن يكون إثبات الاقتطاع جاهزا للمراجعة.",
        )
    elif float(baseline.get("net_tax_due") or 0) > 0:
        add_step(
            4,
            "Confirm the filing and payment deadline before submitting.",
            "The calculation shows net tax due, so verify the official deadline and payment steps before filing.",
            "تأكد من موعد التقديم والدفع قبل الإرسال.",
            "الحساب يظهر ضريبة مستحقة، لذلك تحقق من الموعد الرسمي وخطوات الدفع قبل التقديم.",
        )

    if not steps:
        add_step(
            5,
            "Review the calculated scenarios and keep all supporting documents.",
            "Your profile is complete enough for the advisor, but the final filing should still be checked against official requirements.",
            "راجع السيناريوهات المحسوبة واحتفظ بكل المستندات الداعمة.",
            "ملفك مكتمل بما يكفي للمستشار، لكن يجب مراجعة التقديم النهائي مع المتطلبات الرسمية.",
        )

    if lang == "ar":
        narrative = (
            "تعذر قراءة خطة نموذج المستشار بصيغة JSON، لذلك بنى بيان قائمة محافظة "
            "من ملفك الضريبي ومستنداتك والحساب الحتمي."
        )
    else:
        narrative = (
            "I could not parse the advisor model's plan JSON, so Bayyan built a "
            "conservative checklist from your tax profile, documents, and deterministic calculation."
        )
    return {"steps": steps[:5], "narrative": narrative}


# ── Node 1: Gather Profile ───────────────────────────────────────────────────


async def gather_profile(state: AdvisorState, config: RunnableConfig) -> dict[str, Any]:
    db = _db_from(config)
    profile_id = state["tax_profile_id"]

    profile = await db.get(TaxProfile, profile_id)
    if profile is None:
        # The route should have 404'd already; defensive guard.
        return {"errors": _append_error(state, "tax_profile_not_found")}

    income_rows = (
        await db.execute(select(IncomeSource).where(IncomeSource.tax_profile_id == profile_id))
    ).scalars().all()
    deduction_rows = (
        await db.execute(select(Deduction).where(Deduction.tax_profile_id == profile_id))
    ).scalars().all()
    document_rows = (
        await db.execute(select(Document).where(Document.user_id == profile.user_id))
    ).scalars().all()

    documents_summary = {
        "total": len(document_rows),
        "by_type": _count_by(document_rows, lambda d: d.document_type),
        "by_status": _count_by(document_rows, lambda d: d.processing_status),
    }

    return {
        "user_id": profile.user_id,
        "profile": {
            "tax_year": profile.tax_year,
            "marital_status": profile.marital_status,
            "num_dependents": profile.num_dependents,
            "filing_status": profile.filing_status,
            "residency_status": profile.residency_status,
            "claims_dependents_exemption": profile.claims_dependents_exemption,
            "claim_spouse_expense_exemption": profile.claim_spouse_expense_exemption,
            "disability_exemption_count": profile.disability_exemption_count,
        },
        "income_rows": [
            {
                "id": str(row.id),
                "type": row.type,
                "amount": float(row.amount),
                "tax_withheld": float(row.tax_withheld or 0),
                "employer_name": row.employer_name,
                "description": row.description,
            }
            for row in income_rows
        ],
        "deduction_rows": [
            {
                "id": str(row.id),
                "category": row.category,
                "amount": float(row.amount),
                "date": row.date.isoformat() if row.date else None,
                "description": row.description,
                "document_id": str(row.document_id) if row.document_id else None,
            }
            for row in deduction_rows
        ],
        "documents_summary": documents_summary,
    }


def _count_by(rows: list[Any], key) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        k = key(row) or "unknown"
        out[k] = out.get(k, 0) + 1
    return out


# ── Node 2: Check Completeness ───────────────────────────────────────────────


async def check_completeness(state: AdvisorState, config: RunnableConfig) -> dict[str, Any]:
    missing: list[str] = []
    profile = state.get("profile") or {}
    income_rows = state.get("income_rows") or []

    if not profile.get("marital_status"):
        missing.append("marital_status")
    if not profile.get("residency_status"):
        missing.append("residency_status")
    if profile.get("num_dependents") is None:
        missing.append("num_dependents")
    if not income_rows:
        missing.append("income_sources")

    return {
        "missing_fields": missing,
        "completeness_status": "complete" if not missing else "incomplete",
    }


def completeness_router(state: AdvisorState) -> str:
    """Conditional edge: short-circuit if profile is incomplete."""
    if state.get("completeness_status") == "incomplete":
        return "end"
    return "continue"


# ── Node 3: Analyze Deductions (LLM + RAG) ───────────────────────────────────


async def analyze_deductions(state: AdvisorState, config: RunnableConfig) -> dict[str, Any]:
    lang = state.get("lang", "ar")
    try:
        question = _build_deduction_query(state)
        _chunks, legal_context = await asyncio.to_thread(
            retrieve_with_context, question, 5, "law", lang
        )

        profile_summary = json.dumps(
            {
                "profile": state.get("profile"),
                "income_rows": state.get("income_rows"),
                "current_deductions": state.get("deduction_rows"),
            },
            ensure_ascii=False,
        )

        result = await complete_json(
            prompts.deduction_system(lang),
            prompts.deduction_user(profile_summary, legal_context),
        )
        if result.get("error") == "parse_failed":
            return {
                "deduction_findings": _fallback_deduction_findings(state),
                "errors": _append_error(state, "deductions:llm_parse_failed"),
            }
        return {"deduction_findings": result}
    except Exception as exc:  # noqa: BLE001 — soft-fail per plan
        logger.exception("analyze_deductions failed")
        return {
            "deduction_findings": _fallback_deduction_findings(state),
            "errors": _append_error(state, f"deductions:{type(exc).__name__}"),
        }


def _build_deduction_query(state: AdvisorState) -> str:
    profile = state.get("profile") or {}
    income_types = sorted({row["type"] for row in state.get("income_rows") or []})
    current_cats = sorted({row["category"] for row in state.get("deduction_rows") or []})
    return (
        "خصومات ضريبة الدخل في الأردن المادة 20 — "
        f"حالة اجتماعية: {profile.get('marital_status')}, "
        f"معالون: {profile.get('num_dependents')}, "
        f"أنواع الدخل: {income_types}, "
        f"الخصومات الحالية: {current_cats}"
    )


# ── Node 4: Run Scenarios (deterministic) ────────────────────────────────────


async def run_scenarios(state: AdvisorState, config: RunnableConfig) -> dict[str, Any]:
    tax_input = _build_tax_input(state)
    baseline = calculate_tax(tax_input)
    scenarios = model_scenarios(tax_input)

    baseline_tax = baseline.tax_liability
    return {
        "baseline_breakdown": _serialize_breakdown(baseline),
        "scenarios": [
            {
                "label": s.label,
                "gross_income": s.result.gross_income,
                "taxable_income": s.result.taxable_income,
                "tax_liability": s.result.tax_liability,
                "delta_vs_baseline": round(s.result.tax_liability - baseline_tax, 3),
                "effective_rate": s.result.effective_rate,
                "marginal_rate": s.result.marginal_rate,
            }
            for s in scenarios
        ],
    }


def _build_tax_input(state: AdvisorState) -> TaxInput:
    profile = state.get("profile") or {}
    income_rows = state.get("income_rows") or []
    deduction_rows = state.get("deduction_rows") or []
    return build_tax_input(profile, income_rows, deduction_rows)


def _serialize_breakdown(b) -> dict[str, Any]:
    return {
        "gross_income": b.gross_income,
        "personal_exemption": b.personal_exemption,
        "family_exemption": b.family_exemption,
        "expense_exemption": b.expense_exemption,
        "disability_exemption": b.disability_exemption,
        "total_exemptions": b.total_exemptions,
        "deductions_allowed": {k.value: v for k, v in b.deductions_allowed.items()},
        "deductions_disallowed": {k.value: v for k, v in b.deductions_disallowed.items()},
        "total_deductions": b.total_deductions,
        "taxable_income": b.taxable_income,
        "bracket_breakdown": b.bracket_breakdown,
        "national_contribution": b.national_contribution,
        "tax_liability": b.tax_liability,
        "total_tax_withheld": b.total_tax_withheld,
        "net_tax_due": b.net_tax_due,
        "refund_due": b.refund_due,
        "effective_rate": b.effective_rate,
        "marginal_rate": b.marginal_rate,
    }


# ── Node 5: Assess Risk (LLM + RAG) ──────────────────────────────────────────


async def assess_risk(state: AdvisorState, config: RunnableConfig) -> dict[str, Any]:
    lang = state.get("lang", "ar")
    try:
        _chunks, guidance_context = await asyncio.to_thread(
            retrieve_with_context,
            "مؤشرات تدقيق ضريبة الدخل والمستندات المطلوبة",
            3,
            "guidance",
            lang,
        )

        profile_summary = json.dumps(
            {
                "profile": state.get("profile"),
                "income_rows": state.get("income_rows"),
                "deduction_rows": state.get("deduction_rows"),
                "documents_summary": state.get("documents_summary"),
            },
            ensure_ascii=False,
        )
        findings_json = json.dumps(state.get("deduction_findings") or {}, ensure_ascii=False)
        scenarios_json = json.dumps(state.get("scenarios") or [], ensure_ascii=False)

        result = await complete_json(
            prompts.risk_system(lang),
            prompts.risk_user(profile_summary, findings_json, scenarios_json, guidance_context),
        )
        if result.get("error") == "parse_failed":
            return {
                "risk_assessment": {"flags": [], "narrative": ""},
                "errors": _append_error(state, "risk:llm_parse_failed"),
            }
        return {"risk_assessment": result}
    except Exception as exc:  # noqa: BLE001
        logger.exception("assess_risk failed")
        return {
            "risk_assessment": {"flags": [], "narrative": ""},
            "errors": _append_error(state, f"risk:{type(exc).__name__}"),
        }


# ── Node 6: Generate Plan (LLM) ──────────────────────────────────────────────


async def generate_plan(state: AdvisorState, config: RunnableConfig) -> dict[str, Any]:
    lang = state.get("lang", "ar")
    try:
        profile_summary = json.dumps(
            {
                "profile": state.get("profile"),
                "income_rows": state.get("income_rows"),
                "deduction_rows": state.get("deduction_rows"),
                "documents_summary": state.get("documents_summary"),
            },
            ensure_ascii=False,
        )
        findings_json = json.dumps(state.get("deduction_findings") or {}, ensure_ascii=False)
        scenarios_json = json.dumps(state.get("scenarios") or [], ensure_ascii=False)
        risk_json = json.dumps(state.get("risk_assessment") or {}, ensure_ascii=False)

        result = await complete_json(
            prompts.plan_system(lang),
            prompts.plan_user(profile_summary, findings_json, scenarios_json, risk_json),
        )
        if result.get("error") == "parse_failed":
            return {
                "action_plan": _fallback_action_plan(state),
                "errors": _append_error(state, "plan:llm_parse_failed"),
            }
        return {"action_plan": result}
    except Exception as exc:  # noqa: BLE001
        logger.exception("generate_plan failed")
        return {
            "action_plan": _fallback_action_plan(state),
            "errors": _append_error(state, f"plan:{type(exc).__name__}"),
        }
