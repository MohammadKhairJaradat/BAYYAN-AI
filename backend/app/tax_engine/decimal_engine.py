"""Exact arithmetic over the existing BAYYAN demonstration rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.money import format_money, format_rate, parse_money
from app.models import DeductionCategory
from app.tax_engine import TaxInput

DEMO_RULESET_ID = "bayyan-demo-legacy-v1"
SUPPORTED_DEMO_YEARS = frozenset({2025, 2026})
ZERO = Decimal("0")
BRACKETS = (
    (Decimal("5000"), Decimal("0.05")),
    (Decimal("10000"), Decimal("0.10")),
    (Decimal("15000"), Decimal("0.15")),
    (Decimal("20000"), Decimal("0.20")),
    (Decimal("1000000"), Decimal("0.25")),
    (None, Decimal("0.30")),
)
ARTICLE_9_CATEGORIES = frozenset({
    DeductionCategory.MEDICAL, DeductionCategory.EDUCATION,
    DeductionCategory.RENT, DeductionCategory.HOUSING_INTEREST,
    DeductionCategory.HOUSING_MURABAHA,
})
EXPENSE_ORDER = (
    DeductionCategory.MEDICAL, DeductionCategory.EDUCATION,
    DeductionCategory.RENT, DeductionCategory.HOUSING_INTEREST,
    DeductionCategory.HOUSING_MURABAHA,
)


@dataclass(frozen=True)
class DecimalTaxResult:
    tax_year: int
    gross_income: Decimal
    personal_exemption: Decimal
    family_exemption: Decimal
    expense_exemption: Decimal
    disability_exemption: Decimal
    total_exemptions: Decimal
    deductions_allowed: dict[DeductionCategory, Decimal]
    deductions_disallowed: dict[DeductionCategory, Decimal]
    total_deductions: Decimal
    taxable_income: Decimal
    bracket_breakdown: list[dict]
    tax_before_rounding: Decimal
    national_contribution: Decimal
    tax_liability: Decimal
    total_tax_withheld: Decimal
    net_tax_due: Decimal
    refund_due: Decimal
    effective_rate: Decimal
    marginal_rate: Decimal

    def to_payload(self) -> dict:
        money_fields = (
            "gross_income", "personal_exemption", "family_exemption",
            "expense_exemption", "disability_exemption", "total_exemptions",
            "total_deductions", "taxable_income", "national_contribution",
            "tax_liability", "total_tax_withheld", "net_tax_due", "refund_due",
        )
        result = {field: format_money(getattr(self, field)) for field in money_fields}
        result.update({
            "tax_year": self.tax_year,
            "ruleset_id": DEMO_RULESET_ID,
            "official_filing": False,
            "tax_before_rounding": format_rate(self.tax_before_rounding),
            "effective_rate": format_rate(self.effective_rate),
            "marginal_rate": format_rate(self.marginal_rate),
            "deductions_allowed": {key.value: format_money(value) for key, value in self.deductions_allowed.items()},
            "deductions_disallowed": {key.value: format_money(value) for key, value in self.deductions_disallowed.items()},
            "bracket_breakdown": [{
                "from": format_money(row["from"]),
                "to": format_money(row["to"]) if row["to"] is not None else None,
                "rate": format_rate(row["rate"]),
                "income": format_money(row["income"]),
                "tax": format_money(row["tax"]),
            } for row in self.bracket_breakdown],
        })
        return result


def _count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Counts must be non-negative integers")
    return value


def calculate_decimal(inputs: TaxInput, *, tax_year: int) -> DecimalTaxResult:
    """Same existing rule formulas, with exact inputs and three-fils output."""
    if tax_year not in SUPPORTED_DEMO_YEARS:
        raise ValueError("No demonstration ruleset is configured for this tax year")
    gross = parse_money(inputs.gross_income)
    withheld = parse_money(inputs.tax_withheld)
    dependents = _count(inputs.num_dependents)
    disability_count = _count(inputs.disability_exemption_count)
    if inputs.residency_status not in {"resident", "nonresident_jordanian", "nonresident_other"}:
        raise ValueError("Unsupported residency status")

    deductions: dict[DeductionCategory, Decimal] = {}
    for raw_category, raw_amount in inputs.deductions.items():
        category = DeductionCategory(raw_category)
        amount = parse_money(raw_amount)
        if amount:
            deductions[category] = deductions.get(category, ZERO) + amount

    personal = Decimal("9000") if inputs.residency_status == "resident" else ZERO
    family = Decimal("9000") if personal and inputs.claims_dependents_exemption else ZERO
    eligible = sum((amount for category, amount in deductions.items() if category in ARTICLE_9_CATEGORIES), ZERO)
    allowance = Decimal("1000")
    if inputs.claim_spouse_expense_exemption:
        allowance += Decimal("1000")
    allowance += min(Decimal(dependents) * Decimal("1000"), Decimal("3000"))
    expense = min(eligible, allowance, max(ZERO, Decimal("23000") - personal - family)) if personal else ZERO
    disability = Decimal(disability_count) * Decimal("2000") if personal else ZERO
    exemptions = personal + family + expense + disability
    income_after_exemptions = max(ZERO, gross - exemptions)

    allowed: dict[DeductionCategory, Decimal] = {}
    disallowed: dict[DeductionCategory, Decimal] = {}
    remaining = expense
    for category in EXPENSE_ORDER:
        amount = deductions.get(category, ZERO)
        used = min(amount, remaining)
        if used:
            allowed[category] = used
        if amount > used:
            disallowed[category] = amount - used
        remaining -= used
    for category, amount in deductions.items():
        if category not in ARTICLE_9_CATEGORIES and category != DeductionCategory.DONATIONS:
            disallowed[category] = amount
    donation = deductions.get(DeductionCategory.DONATIONS, ZERO)
    donation_allowed = min(donation, income_after_exemptions * Decimal("0.25"))
    if donation_allowed:
        allowed[DeductionCategory.DONATIONS] = donation_allowed
    if donation > donation_allowed:
        disallowed[DeductionCategory.DONATIONS] = donation - donation_allowed
    taxable = max(ZERO, income_after_exemptions - donation_allowed)

    tax_raw = ZERO
    marginal = ZERO
    previous = ZERO
    breakdown: list[dict] = []
    for upper, rate in BRACKETS:
        if taxable <= previous:
            break
        portion = (min(taxable, upper) if upper is not None else taxable) - previous
        tax = portion * rate
        tax_raw += tax
        marginal = rate
        breakdown.append({"from": previous, "to": upper, "rate": rate, "income": portion, "tax": tax})
        if upper is not None:
            previous = upper
    national = max(ZERO, taxable - Decimal("200000")) * Decimal("0.01")
    total_tax = tax_raw + national
    return DecimalTaxResult(
        tax_year=tax_year, gross_income=gross,
        personal_exemption=personal, family_exemption=family,
        expense_exemption=expense, disability_exemption=disability,
        total_exemptions=exemptions,
        deductions_allowed=allowed, deductions_disallowed=disallowed,
        total_deductions=donation_allowed, taxable_income=taxable,
        bracket_breakdown=breakdown, tax_before_rounding=tax_raw,
        national_contribution=national, tax_liability=total_tax,
        total_tax_withheld=withheld,
        net_tax_due=max(ZERO, total_tax - withheld),
        refund_due=max(ZERO, withheld - total_tax),
        effective_rate=total_tax / gross if gross else ZERO,
        marginal_rate=marginal,
    )
