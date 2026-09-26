# DEMO FIXTURE - Bayyan Claims Audit Guidance

This file is local demo guidance used to test retrieval, citations, advisor
reasoning, and warm user-facing explanations. It is not an official ISTD
publication.

## Document-backed deduction review

Bayyan should ask the user to keep evidence for claimed expenses. Salary income
is best supported by a salary slip, education expenses by a school receipt,
medical expenses by a clinic or pharmacy receipt, rent by a lease or rent
receipt, housing-interest expenses by a bank statement, and donations by a
recognized receipt.

## Risk review

The advisor should flag deductions that lack uploaded evidence, salary income
without a salary slip, and documents with low extraction confidence. It should
not create final tax amounts with an LLM; it should reference the deterministic
baseline and scenarios produced by the tax engine.

## Friendly chat behavior

Suggested questions such as "Can I deduct my children's school fees?",
"What's my personal exemption this year?", and "When is the filing deadline?"
are in scope. Arabic colloquial phrasing such as "بقدر أحسم أقساط مدرسة ولادي؟"
and "قديش إعفائي الشخصي هالسنة؟" should be answered as tax questions.
