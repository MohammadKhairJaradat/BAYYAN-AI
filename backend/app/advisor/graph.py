"""LangGraph wiring + orchestrator entry point for the advisor pipeline."""
from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor import nodes
from app.advisor.state import AdvisorState
from app.models.schemas import (
    AdvisorActionStep,
    AdvisorDeductionOpportunity,
    AdvisorReport,
    AdvisorRiskFlag,
    AdvisorScenario,
    TaxCalculationResult,
)

_compiled_graph = None


def build_graph():
    """Build and compile the 6-node advisor graph."""
    graph = StateGraph(AdvisorState)

    graph.add_node("gather_profile", nodes.gather_profile)
    graph.add_node("check_completeness", nodes.check_completeness)
    graph.add_node("analyze_deductions", nodes.analyze_deductions)
    graph.add_node("run_scenarios", nodes.run_scenarios)
    graph.add_node("assess_risk", nodes.assess_risk)
    graph.add_node("generate_plan", nodes.generate_plan)

    graph.add_edge(START, "gather_profile")
    graph.add_edge("gather_profile", "check_completeness")
    graph.add_conditional_edges(
        "check_completeness",
        nodes.completeness_router,
        {"continue": "analyze_deductions", "end": END},
    )
    graph.add_edge("analyze_deductions", "run_scenarios")
    graph.add_edge("run_scenarios", "assess_risk")
    graph.add_edge("assess_risk", "generate_plan")
    graph.add_edge("generate_plan", END)

    return graph.compile()


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


async def run_advisor(
    tax_profile_id: uuid.UUID,
    db: AsyncSession,
    *,
    lang: str = "ar",
) -> AdvisorReport:
    """Run the full advisor pipeline and assemble the response payload."""
    graph = _get_graph()
    initial_state: AdvisorState = {
        "tax_profile_id": tax_profile_id,
        "lang": lang,
        "errors": [],
    }
    final_state: dict[str, Any] = await graph.ainvoke(
        initial_state, config={"configurable": {"db": db}}
    )

    return _assemble_report(tax_profile_id, lang, final_state)


def _assemble_report(
    tax_profile_id: uuid.UUID, lang: str, state: dict[str, Any]
) -> AdvisorReport:
    status = state.get("completeness_status", "complete")

    if status == "incomplete":
        return AdvisorReport(
            tax_profile_id=tax_profile_id,
            lang=lang,
            status="incomplete",
            missing_fields=state.get("missing_fields") or [],
            errors=state.get("errors") or [],
        )

    baseline_dict = state.get("baseline_breakdown") or {}
    baseline = (
        TaxCalculationResult(tax_profile_id=tax_profile_id, **baseline_dict)
        if baseline_dict
        else None
    )

    scenarios = [
        AdvisorScenario(**s) for s in (state.get("scenarios") or [])
    ]

    deduction_findings = state.get("deduction_findings") or {}
    opportunities = [
        AdvisorDeductionOpportunity(**op)
        for op in (deduction_findings.get("opportunities") or [])
        if isinstance(op, dict) and "category" in op and "description" in op
    ]

    risk_assessment = state.get("risk_assessment") or {}
    risk_flags = [
        AdvisorRiskFlag(**f)
        for f in (risk_assessment.get("flags") or [])
        if isinstance(f, dict) and "severity" in f and "issue" in f
    ]

    action_plan = state.get("action_plan") or {}
    steps = [
        AdvisorActionStep(**step)
        for step in (action_plan.get("steps") or [])
        if isinstance(step, dict) and "priority" in step and "action" in step
    ]

    narratives = {
        "deductions": deduction_findings.get("narrative", "") or "",
        "risk": risk_assessment.get("narrative", "") or "",
        "plan": action_plan.get("narrative", "") or "",
    }

    return AdvisorReport(
        tax_profile_id=tax_profile_id,
        lang=lang,
        status="complete",
        baseline=baseline,
        scenarios=scenarios,
        deduction_opportunities=opportunities,
        risk_flags=risk_flags,
        action_plan=steps,
        narratives=narratives,
        errors=state.get("errors") or [],
    )
