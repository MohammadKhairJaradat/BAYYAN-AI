from decimal import Decimal

from app.models import DeductionCategory
from app.tax_engine import TaxInput, calculate_tax


def test_single_resident_gets_personal_exemption_only():
    result = calculate_tax(TaxInput(gross_income=30_000))

    assert result.personal_exemption == 9_000
    assert result.family_exemption == 0
    assert result.expense_exemption == 0
    assert result.taxable_income == 21_000
    assert result.tax_liability == 2_750


def test_article_9_expenses_are_capped_by_actual_expenses_and_allowance():
    result = calculate_tax(
        TaxInput(
            gross_income=40_000,
            num_dependents=4,
            claims_dependents_exemption=True,
            claim_spouse_expense_exemption=True,
            deductions={
                DeductionCategory.MEDICAL: 5_000,
                DeductionCategory.RENT: 2_000,
            },
        )
    )

    assert result.personal_exemption == 9_000
    assert result.family_exemption == 9_000
    assert result.expense_exemption == 5_000
    assert result.total_exemptions == 23_000
    assert result.deductions_disallowed[DeductionCategory.RENT] == 2_000


def test_disability_exemption_adds_above_article_9_cap():
    result = calculate_tax(
        TaxInput(
            gross_income=40_000,
            num_dependents=3,
            claims_dependents_exemption=True,
            claim_spouse_expense_exemption=True,
            disability_exemption_count=1,
            deductions={DeductionCategory.EDUCATION: 5_000},
        )
    )

    assert result.expense_exemption == 5_000
    assert result.disability_exemption == 2_000
    assert result.total_exemptions == 25_000


def test_donations_are_capped_after_exemptions():
    result = calculate_tax(
        TaxInput(
            gross_income=100_000,
            deductions={DeductionCategory.DONATIONS: 50_000},
        )
    )

    assert result.deductions_allowed[DeductionCategory.DONATIONS] == 22_750
    assert result.deductions_disallowed[DeductionCategory.DONATIONS] == 27_250
    assert result.taxable_income == 68_250


def test_withheld_tax_reduces_due_or_creates_refund():
    result = calculate_tax(TaxInput(gross_income=20_000, tax_withheld=1_000))

    assert result.tax_liability == 900
    assert result.total_tax_withheld == 1_000
    assert result.net_tax_due == 0
    assert result.refund_due == 100


def test_nonresident_does_not_receive_article_9_exemptions():
    result = calculate_tax(
        TaxInput(
            gross_income=20_000,
            residency_status="nonresident_other",
            claims_dependents_exemption=True,
            deductions={DeductionCategory.MEDICAL: 2_000},
        )
    )

    assert result.total_exemptions == 0
    assert result.deductions_disallowed[DeductionCategory.MEDICAL] == 2_000


def test_decimal_and_string_values_are_preserved():
    result = calculate_tax(
        TaxInput(
            gross_income=Decimal("30000.555"),
            tax_withheld="1000.125",
            deductions={DeductionCategory.DONATIONS: "1,000.555"},
        )
    )

    assert result.gross_income == 30000.555
    assert result.deductions_allowed[DeductionCategory.DONATIONS] == 1000.555
    assert result.taxable_income == 20000
    assert result.total_tax_withheld == 1000.125
    assert result.net_tax_due == 1499.875


def test_null_invalid_negative_and_nonfinite_values_are_safe_zero():
    result = calculate_tax(
        TaxInput(
            gross_income="-500.75",
            num_dependents="-2",
            disability_exemption_count=float("inf"),
            tax_withheld=float("nan"),
            deductions={
                DeductionCategory.MEDICAL: None,
                DeductionCategory.RENT: -200,
                DeductionCategory.DONATIONS: "not-a-number",
                DeductionCategory.INSURANCE: float("inf"),
            },
        )
    )

    assert result.gross_income == 0
    assert result.taxable_income == 0
    assert result.tax_liability == 0
    assert result.total_tax_withheld == 0
    assert result.net_tax_due == 0
    assert result.deductions_allowed == {}
    assert result.deductions_disallowed == {}


def test_missing_deductions_do_not_crash():
    result = calculate_tax(TaxInput(gross_income=20_000, deductions=None))

    assert result.gross_income == 20_000
    assert result.taxable_income == 11_000
    assert result.tax_liability == 900
