"""Recorded S06 tax-engine outputs before the S07 Decimal transition."""

import pytest

from app.models import DeductionCategory
from app.tax_engine import TaxInput, calculate_tax


@pytest.mark.parametrize("gross,taxable,liability", [
    ("0", "0.000", "0.000"),
    ("9000", "0.000", "0.000"),
    ("18000", "9000.000", "650.000"),
    ("23000", "14000.000", "1350.000"),
    ("25000", "16000.000", "1700.000"),
    ("28000", "19000.000", "2300.000"),
    ("33000", "24000.000", "3500.000"),
    ("50000", "41000.000", "7750.000"),
    ("250000", "241000.000", "58160.000"),
])
def test_recorded_bracket_boundaries(gross, taxable, liability):
    result = calculate_tax(TaxInput(gross_income=gross))
    assert f"{result.taxable_income:.3f}" == taxable
    assert f"{result.tax_liability:.3f}" == liability


def test_recorded_fractional_withholding_and_donations():
    result = calculate_tax(TaxInput(
        gross_income="50000.125",
        tax_withheld="500.333",
        deductions={
            DeductionCategory.MEDICAL: "123.456",
            DeductionCategory.DONATIONS: "456.789",
        },
    ))
    assert f"{result.taxable_income:.3f}" == "40419.880"
    assert f"{result.tax_liability:.3f}" == "7604.970"
    assert f"{result.net_tax_due:.3f}" == "7104.637"
