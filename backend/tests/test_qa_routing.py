from types import SimpleNamespace

import pytest

from app.rag import qa


OLD_NO_SOURCE_FALLBACK = "لم أجد مصادر قانونية ذات صلة للإجابة على هذا السؤال."
PROVIDER = "gemini"
MODEL = "gemini-2.5-flash"


def _chunk(citation: str = "Article 1", score: float = 0.91):
    return SimpleNamespace(
        citation=citation,
        score=score,
        text="نص قانوني عربي عن ضريبة الدخل والإعفاءات والشرائح.",
    )


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def _fake_call_llm(
        provider,
        user_message,
        model,
        system_prompt=qa.SYSTEM_PROMPT,
        max_tokens=None,
    ):
        calls.append(
            {
                "provider": provider,
                "user_message": user_message,
                "model": model,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
            }
        )
        return f"LLM answer from {model}"

    monkeypatch.setattr(qa, "_call_llm", _fake_call_llm)
    return calls


def test_direct_chat_bypasses_rag(monkeypatch, fake_llm):
    def fail_retrieve(*args, **kwargs):
        raise AssertionError("direct chat should not call retrieval")

    monkeypatch.setattr(qa, "retrieve_with_context", fail_retrieve)

    result = qa.answer("شو ممكن تساعدني؟", provider=PROVIDER, model=MODEL)

    assert result["answer"] == f"LLM answer from {MODEL}"
    assert result["provider"] == PROVIDER
    assert result["model"] == MODEL
    assert result["sources"] == []
    assert fake_llm[0]["system_prompt"] == qa.DIRECT_CHAT_PROMPT


@pytest.mark.parametrize(
    "question",
    [
        "How are you?",
        "How's it going?",
        "How are things?",
        "Are you there?",
        "Nice to meet you",
        "Good afternoon",
        "It is how are you?",
    ],
)
def test_english_small_talk_routes_as_direct_chat(question):
    assert qa.classify_chat_intent(question) == "direct_chat"


@pytest.mark.parametrize(
    "question",
    [
        "كيفك؟",
        "كيف حالك؟",
        "شو أخبارك؟",
        "ايش اخبارك؟",
        "صباح الخير",
        "مساء الخير",
        "تشرفت",
    ],
)
def test_arabic_small_talk_routes_as_direct_chat(question):
    assert qa.classify_chat_intent(question) == "direct_chat"


def test_small_talk_direct_chat_bypasses_rag(monkeypatch, fake_llm):
    def fail_retrieve(*args, **kwargs):
        raise AssertionError("small talk should not call retrieval")

    monkeypatch.setattr(qa, "retrieve_with_context", fail_retrieve)

    result = qa.answer("How are you?", lang="en", provider=PROVIDER, model=MODEL)

    assert result["answer"] == f"LLM answer from {MODEL}"
    assert result["sources"] == []
    assert fake_llm[0]["system_prompt"] == qa.DIRECT_CHAT_PROMPT


@pytest.mark.parametrize(
    ("question", "expected_intent"),
    [
        ("Hi, can I deduct school fees?", "tax_legal_grounded"),
        ("صباح الخير، بقدر أحسم أقساط مدرسة ولادي؟", "tax_legal_grounded"),
        ("كيفك؟ اشرحلي عن الضريبة", "tax_general"),
    ],
)
def test_tax_bearing_greetings_do_not_route_as_small_talk(question, expected_intent):
    assert qa.classify_chat_intent(question) == expected_intent


def test_broad_tax_question_uses_safe_general_answer_when_no_sources(monkeypatch):
    queries = []

    def no_sources(query, **kwargs):
        queries.append(query)
        return [], ""

    def fail_llm(*args, **kwargs):
        raise AssertionError("tax_general without sources should not call the LLM")

    monkeypatch.setattr(qa, "retrieve_with_context", no_sources)
    monkeypatch.setattr(qa, "_call_llm", fail_llm)

    assert qa.classify_chat_intent("مرحبا اشرحلي عن الضريبة؟") == "tax_general"

    result = qa.answer("اشرحلي عن الضريبة؟", provider=PROVIDER, model=MODEL)

    assert len(queries) >= 2
    assert "شرحاً عاماً" in result["answer"]
    assert "لم أجد حالياً مصدراً داخلياً" in result["answer"]
    assert OLD_NO_SOURCE_FALLBACK not in result["answer"]
    assert result["sources"] == []
    assert result["model"] == MODEL


@pytest.mark.parametrize(
    "question",
    [
        "بقدر أحسم أقساط مدرسة ولادي؟",
        "قدّيش إعفائي الشخصي هالسنة؟",
        "إيمتى آخر موعد للتقديم؟",
        "Can I deduct my children's school fees?",
        "What's my personal exemption this year?",
        "When is the filing deadline?",
    ],
)
def test_chat_suggestion_questions_route_as_tax_legal(question):
    assert qa.classify_chat_intent(question) == "tax_legal_grounded"


def test_colloquial_school_fee_question_uses_legal_fallback_not_off_topic(monkeypatch):
    def no_sources(query, **kwargs):
        return [], ""

    def fail_llm(*args, **kwargs):
        raise AssertionError("legal-grounded questions without sources should not call the LLM")

    monkeypatch.setattr(qa, "retrieve_with_context", no_sources)
    monkeypatch.setattr(qa, "_call_llm", fail_llm)

    result = qa.answer("بقدر أحسم أقساط مدرسة ولادي؟", provider=PROVIDER, model=MODEL)

    assert "سؤالك ضريبي وواضح" in result["answer"]
    assert "TaxAI" not in result["answer"]
    assert result["sources"] == []


def test_specific_legal_tax_question_uses_grounded_rag(monkeypatch, fake_llm):
    def retrieve(query, **kwargs):
        return [_chunk("Article 6")], "قانون ضريبة الدخل: الإعفاءات..."

    monkeypatch.setattr(qa, "retrieve_with_context", retrieve)

    result = qa.answer("ما هي إعفاءات ضريبة الدخل؟", provider=PROVIDER, model=MODEL)

    assert result["answer"] == f"LLM answer from {MODEL}"
    assert result["sources"] == [{"citation": "Article 6", "score": 0.91}]
    assert fake_llm[0]["system_prompt"] == qa.SYSTEM_PROMPT
    assert "قانون ضريبة الدخل" in fake_llm[0]["user_message"]


def test_english_grounded_prompt_keeps_english_language_instruction(monkeypatch, fake_llm):
    def retrieve(query, **kwargs):
        return [_chunk("Article 20")], "سياق قانوني عربي عن الخصومات والإعفاءات."

    monkeypatch.setattr(qa, "retrieve_with_context", retrieve)

    result = qa.answer(
        "Can I deduct my children's school fees?",
        lang="en",
        provider=PROVIDER,
        model=MODEL,
    )

    assert result["answer"] == f"LLM answer from {MODEL}"
    assert "Answer in English" in fake_llm[0]["user_message"]
    assert (
        "Question: Can I deduct my children's school fees?"
        in fake_llm[0]["user_message"]
    )
    assert "\nالسؤال:" not in fake_llm[0]["user_message"]


def test_specific_legal_tax_question_requires_sources(monkeypatch):
    def no_sources(query, **kwargs):
        return [], ""

    def fail_llm(*args, **kwargs):
        raise AssertionError("legal-grounded questions without sources should not call the LLM")

    monkeypatch.setattr(qa, "retrieve_with_context", no_sources)
    monkeypatch.setattr(qa, "_call_llm", fail_llm)

    result = qa.answer("ما هي إعفاءات ضريبة الدخل؟", provider=PROVIDER, model=MODEL)

    assert "قاعدة المصادر القانونية الداخلية" in result["answer"]
    assert "الإعفاءات" in result["answer"]
    assert OLD_NO_SOURCE_FALLBACK not in result["answer"]
    assert result["sources"] == []


def test_calculation_question_uses_tax_engine(monkeypatch):
    def no_sources(query, **kwargs):
        return [], ""

    def fail_llm(*args, **kwargs):
        raise AssertionError("tax calculations should not call the chat LLM")

    monkeypatch.setattr(qa, "retrieve_with_context", no_sources)
    monkeypatch.setattr(qa, "_call_llm", fail_llm)

    result = qa.answer("احسب ضريبتي دخلي 20000 دينار", provider=PROVIDER, model=MODEL)

    assert result["provider"] == "tax_engine"
    assert result["model"] is None
    assert result["tax_breakdown"]["gross_income"] == 20000
    assert "نتيجة حساب ضريبة الدخل" in result["answer"]


def test_contextual_calculation_followup_uses_memory_for_tax_engine(monkeypatch):
    def no_sources(query, **kwargs):
        return [], ""

    def fail_llm(*args, **kwargs):
        raise AssertionError("contextual tax calculations should not call the chat LLM")

    monkeypatch.setattr(qa, "retrieve_with_context", no_sources)
    monkeypatch.setattr(qa, "_call_llm", fail_llm)

    result = qa.answer(
        "What if I am married?",
        provider=PROVIDER,
        model=MODEL,
        conversation_context=(
            "Session memory summary:\n"
            "Known facts:\n"
            "- User annual salary: 20000 JOD.\n"
        ),
    )

    assert result["provider"] == "tax_engine"
    assert result["tax_breakdown"]["gross_income"] == 20000


def test_affirmative_followup_after_calculation_offer_uses_tax_engine(monkeypatch):
    def no_sources(query, **kwargs):
        return [], ""

    def fail_llm(*args, **kwargs):
        raise AssertionError("affirmative calculation follow-ups should not call the chat LLM")

    monkeypatch.setattr(qa, "retrieve_with_context", no_sources)
    monkeypatch.setattr(qa, "_call_llm", fail_llm)

    result = qa.answer(
        "\u0646\u0639\u0645",
        provider=PROVIDER,
        model=MODEL,
        conversation_context=(
            "Recent prior messages:\n"
            "User: My annual salary is 50 thousand JOD.\n"
            "Assistant: Would you like me to calculate your estimated income tax?"
        ),
    )

    assert result["provider"] == "tax_engine"
    assert result["tax_breakdown"]["gross_income"] == 50000


def test_extract_tax_inputs_preserves_signed_decimal_amount():
    inputs = qa._extract_tax_inputs("Calculate my tax if salary is -500.75 JOD")

    assert inputs.gross_income == -500.75


def test_extract_tax_inputs_parses_thousand_amount_words():
    inputs_en = qa._extract_tax_inputs("Calculate my tax if salary is 50 thousand JOD")
    inputs_ar = qa._extract_tax_inputs(
        "\u0627\u062d\u0633\u0628 \u0636\u0631\u064a\u0628\u062a\u064a "
        "\u0631\u0627\u062a\u0628\u064a 50 \u0627\u0644\u0641 "
        "\u062f\u064a\u0646\u0627\u0631"
    )

    assert inputs_en.gross_income == 50000
    assert inputs_ar.gross_income == 50000


def test_memory_recall_uses_direct_llm_with_context(monkeypatch, fake_llm):
    def fail_retrieve(*args, **kwargs):
        raise AssertionError("memory recall should not call retrieval")

    monkeypatch.setattr(qa, "retrieve_with_context", fail_retrieve)

    result = qa.answer(
        "What was my salary?",
        provider=PROVIDER,
        model=MODEL,
        conversation_context="Session memory summary:\nKnown facts:\n- Salary: 20000 JOD.",
    )

    assert result["answer"] == f"LLM answer from {MODEL}"
    assert "Salary: 20000 JOD" in fake_llm[0]["user_message"]
    assert "Current user question" in fake_llm[0]["user_message"]


def test_advisor_report_recall_uses_direct_llm_with_context(monkeypatch, fake_llm):
    def fail_retrieve(*args, **kwargs):
        raise AssertionError("advisor report recall should not call law retrieval")

    monkeypatch.setattr(qa, "retrieve_with_context", fail_retrieve)

    result = qa.answer(
        "What does my advisor report say?",
        provider=PROVIDER,
        model=MODEL,
        conversation_context=(
            "Authenticated account context.\n"
            '{"latest_advisor_report":{"status":"fresh","report":{"status":"complete"}}}'
        ),
    )

    assert result["answer"] == f"LLM answer from {MODEL}"
    assert "latest_advisor_report" in fake_llm[0]["user_message"]
    assert fake_llm[0]["system_prompt"] == qa.DIRECT_CHAT_PROMPT


def test_resolve_chat_model_rejects_unsupported_model():
    with pytest.raises(ValueError):
        qa.resolve_chat_model("openai", "gpt-3.5-turbo")


def test_off_topic_redirects_without_rag_or_llm(monkeypatch):
    def fail_retrieve(*args, **kwargs):
        raise AssertionError("off-topic prompts should not call retrieval")

    def fail_llm(*args, **kwargs):
        raise AssertionError("off-topic prompts should not call the LLM")

    monkeypatch.setattr(qa, "retrieve_with_context", fail_retrieve)
    monkeypatch.setattr(qa, "_call_llm", fail_llm)

    result = qa.answer("اكتبلي قصيدة عن البحر", provider=PROVIDER, model=MODEL)

    assert "TaxAI" in result["answer"]
    assert "ضريبة الدخل" in result["answer"]
    assert result["sources"] == []
    assert result["model"] == MODEL
