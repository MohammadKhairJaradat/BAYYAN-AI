"""Deterministic Jordanian individual income-tax calculations.

This module implements the project's current coded rules, including exemptions,
progressive brackets, donations, and national contribution. Legal applicability
and year-specific rule selection require separate verification; this module is
not evidence of official approval. Computation is unchanged by this note.
"""

from __future__ import annotations
from decimal import Decimal, InvalidOperation
import math
from dataclasses import dataclass, field
from typing import Optional

from app.models import DeductionCategory, MaritalStatus


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

TAX_BRACKETS = [
    (5_000,   0.05),
    (10_000,  0.10),
    (15_000,  0.15),
    (20_000,  0.20),
    (1_000_000, 0.25),
    (math.inf, 0.30),
]

PERSONAL_EXEMPTION = 9_000.0
FAMILY_EXEMPTION = 9_000.0
MAX_TOTAL_EXEMPTIONS = 23_000.0

SELF_ALLOWANCE = 1_000.0
SPOUSE_ALLOWANCE = 1_000.0
CHILD_ALLOWANCE = 1_000.0
MAX_CHILD_ALLOWANCE = 3_000.0
DISABILITY_EXEMPTION = 2_000.0

DONATIONS_CAP_RATE = 0.25

ARTICLE_9_EXPENSE_CATEGORIES = {
    DeductionCategory.MEDICAL,
    DeductionCategory.EDUCATION,
    DeductionCategory.RENT,
    DeductionCategory.HOUSING_INTEREST,
    DeductionCategory.HOUSING_MURABAHA,
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TaxInput:
    gross_income: float
    marital_status: MaritalStatus = MaritalStatus.SINGLE
    num_dependents: int = 0
    residency_status: str = "resident"
    claims_dependents_exemption: bool = False
    claim_spouse_expense_exemption: bool = False
    disability_exemption_count: int = 0
    tax_withheld: float | Decimal | str = Decimal("0")
    deductions: dict[DeductionCategory, float] = field(default_factory=dict)


@dataclass
class TaxBreakdown:
    gross_income: float

    personal_exemption: float
    family_exemption: float
    expense_exemption: float
    disability_exemption: float
    total_exemptions: float

    deductions_allowed: dict
    deductions_disallowed: dict
    total_deductions: float

    taxable_income: float

    bracket_breakdown: list
    tax_before_rounding: float
    national_contribution: float
    tax_liability: float
    total_tax_withheld: float
    net_tax_due: float
    refund_due: float

    effective_rate: float
    marginal_rate: float


# ─────────────────────────────────────────────────────────────────────────────
# Core Logic
# ─────────────────────────────────────────────────────────────────────────────

def _eligible_for_article_9_exemptions(residency_status: str) -> bool:
    return residency_status == "resident"


def _number(value) -> float:
    if value is None:
        return 0.0

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return 0.0
        value = cleaned.replace(",", "")

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0

    if not amount.is_finite():
        return 0.0

    return float(amount)


def _money(value) -> float:
    return max(0.0, _number(value))


def _count(value) -> int:
    return int(_money(value))


def _normalize_deductions(
    deductions: dict[DeductionCategory, float] | None,
) -> dict[DeductionCategory, float]:
    normalized: dict[DeductionCategory, float] = {}
    if not deductions:
        return normalized
    if not hasattr(deductions, "items"):
        return normalized

    for raw_category, raw_amount in deductions.items():
        try:
            category = DeductionCategory(raw_category)
        except (TypeError, ValueError):
            continue

        amount = _money(raw_amount)
        if amount <= 0:
            continue
        normalized[category] = normalized.get(category, 0.0) + amount

    return normalized


def _normalize_inputs(inputs: TaxInput) -> TaxInput:
    return TaxInput(
        gross_income=_money(inputs.gross_income),
        marital_status=inputs.marital_status,
        num_dependents=_count(inputs.num_dependents),
        residency_status=inputs.residency_status or "resident",
        claims_dependents_exemption=bool(inputs.claims_dependents_exemption),
        claim_spouse_expense_exemption=bool(inputs.claim_spouse_expense_exemption),
        disability_exemption_count=_count(inputs.disability_exemption_count),
        tax_withheld=_money(inputs.tax_withheld),
        deductions=_normalize_deductions(inputs.deductions),
    )


def calculate_exemptions(inputs: TaxInput) -> tuple[float, float, float, float]:
    """Article 9 exemptions (Income Tax Law 34/2014, amended by 38/2018).

    Returns ``(personal, family, expense, disability)``:

    - ``personal`` — flat 9,000 for the resident taxpayer.
    - ``family`` — flat 9,000 when ``claims_dependents_exemption`` is set, granted
      to dependents *regardless of their number*. It does NOT scale per child.
    - ``expense`` — the exemption for documented Article-9 expenses
      (medical/education/rent/housing interest/murabaha). The per-person amounts
      (1,000 self + 1,000 spouse + 1,000 per child, children capped at 3,000) only
      size the *ceiling* on those documented expenses — they are NOT a standalone
      per-head cash exemption. So dependents reduce tax only when matching
      documented expenses exist, and the actual exemption is
      ``min(eligible_expenses, expense_allowance, 23,000 − personal − family)``.

    Deductions are pooled by category (``TaxInput.deductions`` is
    ``dict[category, amount]``); the engine is **beneficiary-agnostic** — the
    ``Deduction.beneficiary`` field is display/tracking metadata only and never
    affects this calculation.
    """
    if not _eligible_for_article_9_exemptions(inputs.residency_status):
        return 0.0, 0.0, 0.0, 0.0

    personal = PERSONAL_EXEMPTION
    family = FAMILY_EXEMPTION if inputs.claims_dependents_exemption else 0.0
    num_dependents = _count(inputs.num_dependents)

    expense_allowance = SELF_ALLOWANCE
    if inputs.claim_spouse_expense_exemption:
        expense_allowance += SPOUSE_ALLOWANCE
    expense_allowance += min(
        num_dependents * CHILD_ALLOWANCE,
        MAX_CHILD_ALLOWANCE,
    )

    deductions = _normalize_deductions(inputs.deductions)
    eligible_expenses = sum(
        amount
        for category, amount in deductions.items()
        if category in ARTICLE_9_EXPENSE_CATEGORIES
    )
    remaining_article_9_cap = max(0.0, MAX_TOTAL_EXEMPTIONS - personal - family)
    expense = min(eligible_expenses, expense_allowance, remaining_article_9_cap)

    disability = _count(inputs.disability_exemption_count) * DISABILITY_EXEMPTION

    return personal, family, expense, disability


def allocate_expense_exemption(
    deductions: dict[DeductionCategory, float],
    expense_exemption: float,
) -> tuple[dict[DeductionCategory, float], dict[DeductionCategory, float]]:
    allowed: dict[DeductionCategory, float] = {}
    disallowed: dict[DeductionCategory, float] = {}
    remaining = max(0.0, expense_exemption)

    for category in (
        DeductionCategory.MEDICAL,
        DeductionCategory.EDUCATION,
        DeductionCategory.RENT,
        DeductionCategory.HOUSING_INTEREST,
        DeductionCategory.HOUSING_MURABAHA,
    ):
        amount = _money(deductions.get(category, 0.0))
        if amount <= 0:
            continue
        allowed_amount = min(amount, remaining)
        if allowed_amount > 0:
            allowed[category] = allowed_amount
        if amount > allowed_amount:
            disallowed[category] = amount - allowed_amount
        remaining -= allowed_amount

    return allowed, disallowed


def calculate_donation_deduction(
    donation_amount: float,
    net_income_before_donations: float,
) -> tuple[float, float]:
    donation_amount = _money(donation_amount)
    net_income_before_donations = _money(net_income_before_donations)
    if donation_amount <= 0:
        return 0.0, 0.0
    cap = max(0.0, net_income_before_donations) * DONATIONS_CAP_RATE
    allowed = min(donation_amount, cap)
    return allowed, max(0.0, donation_amount - allowed)


def calculate_tax_on_income(taxable_income):
    taxable_income = _money(taxable_income)
    if taxable_income <= 0:
        return 0.0, [], 0.0

    total_tax = 0.0
    breakdown = []
    marginal_rate = 0.0
    previous_upper = 0.0

    for upper, rate in TAX_BRACKETS:
        if taxable_income <= previous_upper:
            break

        portion = min(taxable_income, upper) - previous_upper
        tax = portion * rate

        total_tax += tax
        marginal_rate = rate

        breakdown.append({
            "from": previous_upper,
            "to": upper if upper != math.inf else None,
            "rate": rate,
            "income": round(portion, 3),
            "tax": round(tax, 3),
        })

        previous_upper = upper

    return total_tax, breakdown, marginal_rate


def calculate_national_contribution(taxable_income: float):
    taxable_income = _money(taxable_income)
    if taxable_income <= 200_000:
        return 0.0
    return (taxable_income - 200_000) * 0.01


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def calculate_tax(inputs: TaxInput) -> TaxBreakdown:

    inputs = _normalize_inputs(inputs)
    deductions = inputs.deductions
    gross = inputs.gross_income

    personal, family, expense, disability = calculate_exemptions(inputs)
    exemptions = personal + family + expense + disability

    income_after_exemptions = max(0.0, gross - exemptions)

    expense_allowed, expense_disallowed = allocate_expense_exemption(
        deductions,
        expense,
    )

    ignored_deductions = {
        category: amount
        for category, amount in deductions.items()
        if category not in ARTICLE_9_EXPENSE_CATEGORIES
        and category != DeductionCategory.DONATIONS
        and amount > 0
    }

    donation_amount = deductions.get(DeductionCategory.DONATIONS, 0.0)
    donation_allowed, donation_disallowed = calculate_donation_deduction(
        donation_amount,
        income_after_exemptions,
    )

    allowed = dict(expense_allowed)
    if donation_allowed > 0:
        allowed[DeductionCategory.DONATIONS] = donation_allowed

    disallowed = {**expense_disallowed, **ignored_deductions}
    if donation_disallowed > 0:
        disallowed[DeductionCategory.DONATIONS] = donation_disallowed

    total_deductions = donation_allowed

    taxable = max(0.0, income_after_exemptions - total_deductions)

    tax_raw, breakdown, marginal_rate = calculate_tax_on_income(taxable)
    national = calculate_national_contribution(taxable)

    total_tax = tax_raw + national
    tax_withheld = inputs.tax_withheld
    net_tax_due = max(0.0, total_tax - tax_withheld)
    refund_due = max(0.0, tax_withheld - total_tax)

    return TaxBreakdown(
        gross_income=round(gross, 3),

        personal_exemption=round(personal, 3),
        family_exemption=round(family, 3),
        expense_exemption=round(expense, 3),
        disability_exemption=round(disability, 3),
        total_exemptions=round(exemptions, 3),

        deductions_allowed={k: round(v, 3) for k, v in allowed.items()},
        deductions_disallowed={k: round(v, 3) for k, v in disallowed.items()},
        total_deductions=round(total_deductions, 3),

        taxable_income=round(taxable, 3),

        bracket_breakdown=breakdown,
        tax_before_rounding=round(tax_raw, 6),
        national_contribution=round(national, 3),
        tax_liability=round(total_tax, 3),
        total_tax_withheld=round(tax_withheld, 3),
        net_tax_due=round(net_tax_due, 3),
        refund_due=round(refund_due, 3),

        effective_rate=round(total_tax / gross, 6) if gross > 0 else 0.0,
        marginal_rate=marginal_rate,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scenario Modeling (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TaxScenario:
    label: str
    inputs: TaxInput
    result: TaxBreakdown


def model_scenarios(
    base_inputs: TaxInput,
    scenarios: Optional[list[tuple[str, TaxInput]]] = None,
):

    if scenarios is None:
        scenarios = _auto_scenarios(base_inputs)

    results = []
    for label, inputs in scenarios:
        result = calculate_tax(inputs)
        results.append(TaxScenario(label, inputs, result))

    results.sort(key=lambda s: s.result.tax_liability)
    return results


def _auto_scenarios(base: TaxInput):
    import copy

    baseline = ("الحالة الحالية", copy.deepcopy(base))

    max_ded = copy.deepcopy(base)
    for cat in DeductionCategory:
        if cat != DeductionCategory.DONATIONS:
            max_ded.deductions[cat] = 10_000  # simulate max
    max_scenario = ("تعظيم الخصومات", max_ded)

    extra_dep = copy.deepcopy(base)
    extra_dep.num_dependents += 1
    extra_dep.claims_dependents_exemption = True
    dep_scenario = ("إضافة معال", extra_dep)

    return [baseline, max_scenario, dep_scenario]
