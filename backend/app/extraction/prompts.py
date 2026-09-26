"""
Shared prompts and schema hints for document extraction.
"""

from __future__ import annotations

from .base import DocumentType

EXTRACTION_SYSTEM_PROMPT = """\
You are a document analysis assistant specializing in Jordanian tax documents.
Analyze the document image and extract the requested fields as a JSON object.
Return ONLY valid JSON - no explanation, no markdown fences.

Required JSON schema:
{
  "vendor": "<string: company/hospital/school/landlord name, or null>",
  "amount": <number: total amount in Jordanian Dinars (JD), or null>,
  "date": "<string: ISO date YYYY-MM-DD, or null>",
  "category": "<one of: medical, education, rent, housing_interest, housing_murabaha, donations, insurance, pension, unknown>",
  "document_type": "<one of: receipt, salary_slip, bank_statement, unknown>",
  "confidence": <number between 0.0 and 1.0: your confidence in the extraction>,
  "raw_text": "<string: all text visible in the document>"
}

Rules:
- amount must be in JD (Jordanian Dinars). Convert if needed.
- If a field is unclear or missing, use null (not empty string).
- confidence should reflect overall extraction quality, not just one field.
- For Arabic text, preserve it as-is in raw_text.
- For salary slips: amount = net salary after deductions.
- For receipts: amount = total paid.
- For bank statements: amount = transaction amount relevant to a deduction.
"""

EXTRACTION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor": {"type": "string", "nullable": True},
        "amount": {"type": "number", "nullable": True},
        "date": {"type": "string", "nullable": True},
        "category": {
            "type": "string",
            "enum": [
                "medical",
                "education",
                "rent",
                "housing_interest",
                "housing_murabaha",
                "donations",
                "insurance",
                "pension",
                "unknown",
            ],
        },
        "document_type": {
            "type": "string",
            "enum": ["receipt", "salary_slip", "bank_statement", "unknown"],
        },
        "confidence": {"type": "number"},
        "raw_text": {"type": "string", "nullable": True},
    },
    "required": [
        "vendor",
        "amount",
        "date",
        "category",
        "document_type",
        "confidence",
        "raw_text",
    ],
}


def build_user_prompt(document_type_hint: DocumentType | None = None) -> str:
    prompt = "Extract the Jordanian tax document fields from this document."
    if document_type_hint and document_type_hint != DocumentType.UNKNOWN:
        prompt += f"\nDocument type hint from user: {document_type_hint.value}"
    return prompt
