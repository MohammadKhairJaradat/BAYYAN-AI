import json
from pathlib import Path

from app.models import DeductionCategory, MaritalStatus
from app.tax_engine import TaxInput, calculate_tax


def test_marketing_example_matches_deterministic_engine():
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "frontend/src/data/marketing-tax-example.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    inputs = fixture["inputs"]
    result = calculate_tax(
        TaxInput(
            gross_income=inputs["gross_income"],
            marital_status=MaritalStatus(inputs["marital_status"]),
            num_dependents=inputs["num_dependents"],
            claims_dependents_exemption=inputs["claims_dependents_exemption"],
            claim_spouse_expense_exemption=inputs["claim_spouse_expense_exemption"],
            deductions={
                DeductionCategory(category): amount
                for category, amount in inputs["deductions"].items()
            },
        )
    )
    for field, expected in fixture["expected"].items():
        assert getattr(result, field) == expected, field
