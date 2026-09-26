"""Shared state passed between advisor LangGraph nodes."""
from __future__ import annotations

import uuid
from typing import Any, TypedDict


class AdvisorState(TypedDict, total=False):
    # Inputs
    tax_profile_id: uuid.UUID
    user_id: uuid.UUID
    lang: str  # "ar" | "en"

    # Node 1 — Gather Profile
    profile: dict[str, Any]
    income_rows: list[dict[str, Any]]
    deduction_rows: list[dict[str, Any]]
    documents_summary: dict[str, Any]

    # Node 2 — Check Completeness
    completeness_status: str  # "complete" | "incomplete"
    missing_fields: list[str]

    # Node 3 — Analyze Deductions
    deduction_findings: dict[str, Any]

    # Node 4 — Run Scenarios
    baseline_breakdown: dict[str, Any]
    scenarios: list[dict[str, Any]]

    # Node 5 — Assess Risk
    risk_assessment: dict[str, Any]

    # Node 6 — Generate Plan
    action_plan: dict[str, Any]

    # Always
    errors: list[str]
