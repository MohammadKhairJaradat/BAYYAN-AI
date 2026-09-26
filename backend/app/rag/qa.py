"""
qa.py — Chat router + RAG-powered Q&A.

Intent routing (classify_chat_intent):
  - tax_calculation    → tax_engine (Python deterministic, no LLM)
  - direct_chat        → LLM only, no RAG (greetings, meta questions)
  - tax_general        → broad educational, RAG + LLM with safe fallback
  - tax_legal_grounded → specific legal questions, RAG required
  - off_topic          → polite redirect, no LLM/RAG

Providers: Anthropic Claude, OpenAI, Google Gemini, Groq.
Provider + model are selected per-request (see resolve_chat_model); the
LLM_PROVIDER / *_CHAT_MODEL settings only supply defaults.

Usage:
    from app.rag.qa import answer
    response = answer("ما هي نسبة ضريبة الدخل على الراتب؟", provider="gemini")
    response = answer("احسب ضريبتي، دخلي 20000 دينار وعندي معالان")
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# تأكد أن backend/ موجود في sys.path
_backend_dir = Path(__file__).resolve().parents[2]  # backend/app/rag → backend/
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
import re
from typing import Literal, Optional

from app.config import settings
from app.integrations.ai.registry import SUPPORTED_CHAT_MODELS as _SUPPORTED_CHAT_MODELS
from app.integrations.ai.registry import SUPPORTED_PROVIDERS as _SUPPORTED_PROVIDER_NAMES

from .limits import LLM_MAX_OUTPUT_TOKENS, PROMPT_CHAR_LIMITS, PROMPT_TOP_K_LIMITS
from .prompts import (
    DIRECT_CHAT_PROMPT,
    GENERAL_TAX_PROMPT,
    LEGAL_NO_SOURCE_AR,
    LEGAL_NO_SOURCE_EN,
    OFF_TOPIC_AR,
    OFF_TOPIC_EN,
    SYSTEM_PROMPT,
    TAX_GENERAL_NO_SOURCE_AR,
    TAX_GENERAL_NO_SOURCE_EN,
    TITLE_SYSTEM_PROMPT_AR,
    TITLE_SYSTEM_PROMPT_EN,
)
from .retriever import retrieve_with_context

logger = logging.getLogger(__name__)

# ── Config — all keys come from settings (config.py reads from .env) ─────────
# Default provider used when a caller doesn't pass one explicitly (e.g. the
# title-generation path). Per-request routing in answer() still wins via the
# `provider` argument.
LLM_PROVIDER = settings.LLM_PROVIDER.lower()

ChatIntent = Literal[
    "direct_chat",
    "tax_general",
    "tax_legal_grounded",
    "tax_calculation",
    "off_topic",
]

_VALID_INTENTS = frozenset(
    {"direct_chat", "tax_general", "tax_legal_grounded", "tax_calculation", "off_topic"}
)



def supported_chat_models() -> dict[str, set[str]]:
    return {provider: set(models) for provider, models in _SUPPORTED_CHAT_MODELS.items()}


def _default_chat_model(provider: str) -> str:
    defaults = {
        "anthropic": settings.ANTHROPIC_CHAT_MODEL,
        "openai": settings.OPENAI_CHAT_MODEL,
        "gemini": settings.GEMINI_CHAT_MODEL,
        "groq": settings.GROQ_CHAT_MODEL,
    }
    try:
        return defaults[provider].strip()
    except KeyError as exc:
        raise ValueError(
            f"Unknown provider: {provider!r}. Choose: anthropic | openai | gemini | groq"
        ) from exc


def resolve_chat_model(provider: str, model: Optional[str] = None) -> str:
    provider = provider.strip().lower()
    if provider not in _SUPPORTED_PROVIDER_NAMES:
        raise ValueError(
            f"Unknown provider: {provider!r}. Choose: anthropic | openai | gemini | groq"
        )

    chosen_model = (model or _default_chat_model(provider)).strip()
    if not chosen_model:
        raise ValueError(f"No chat model configured for provider {provider!r}")

    if model and chosen_model not in _SUPPORTED_CHAT_MODELS[provider]:
        allowed = ", ".join(sorted(_SUPPORTED_CHAT_MODELS[provider]))
        raise ValueError(
            f"Model {chosen_model!r} is not allowed for provider {provider!r}. "
            f"Allowed: {allowed}"
        )
    return chosen_model

# كلمات تدل على أن المستخدم يريد حساباً فعلياً
_CALC_TRIGGERS = re.compile(
    r"احسب|حساب|كم ضريبت|كم راح أدفع|ضريبتي"
    r"|calculate|calculation|compute|how much tax|tax due|tax liability"
    r"|income\s+\d|income\s*=?\s*\d|salary\s+\d|salary\s*=?\s*\d"
    r"|دخل[يه]?\s+\d|دخل[يه]?\s*=?\s*\d"
    r"|راتب[يه]?\s+\d|راتب[يه]?\s*=?\s*\d"
    r"|ودخلي|وراتبي"
    r"|كم\s+ضريبت|كم\s+أدفع|كم\s+تكون\s+ضريبت"
    r"|كم تساوي|كم يكون"
    r"|JD\s*\d|\d\s*JD|JOD\s*\d|\d\s*JOD",
    re.IGNORECASE,
)

# استخراج الأرقام من النص
_ARABIC_INDIC_DIGITS = str.maketrans(
    "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9",
    "01234567890123456789",
)
_THOUSAND_SUFFIXES = {
    "k",
    "thousand",
    "thousands",
    "\u0627\u0644\u0641",
    "\u0623\u0644\u0641",
    "\u0622\u0644\u0627\u0641",
    "\u0627\u0644\u0627\u0641",
}
_THOUSAND_SUFFIX_PATTERN = (
    r"k|thousand|thousands|\u0627\u0644\u0641|\u0623\u0644\u0641"
    r"|\u0622\u0644\u0627\u0641|\u0627\u0644\u0627\u0641"
)
_AMOUNT_TOKEN_PATTERN = (
    rf"([+-]?\d[\d,]*(?:\.\d+)?)\s*({_THOUSAND_SUFFIX_PATTERN})?"
)
_NUMBER = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?")
_NUMBER_AMOUNT_RE = re.compile(_AMOUNT_TOKEN_PATTERN, re.IGNORECASE)
_INCOME_AMOUNT_RE = re.compile(
    r"(?:income|salary|gross income|annual salary|دخل|دخلي|راتب|راتبي)"
    rf"[^+\-\d]{{0,40}}{_AMOUNT_TOKEN_PATTERN}",
    re.IGNORECASE,
)
_CURRENCY_AMOUNT_RE = re.compile(
    rf"{_AMOUNT_TOKEN_PATTERN}\s*(?:JOD|JD|دينار)",
    re.IGNORECASE,
)

_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")

_DIRECT_CHAT_RE = re.compile(
    r"\b(hi|hello|hey|good morning|good evening|who are you|what are you"
    r"|good afternoon|good night|good day|how are you|how are u|how r you"
    r"|how['’]?s it going|how is it going|how are things|how have you been"
    r"|are you there|you there|nice to meet you|good to meet you"
    r"|what['’]?s up(?!\s+with)|whats up(?!\s+with)"
    r"|what can you do|how can you help|what do you do|introduce yourself|help me)\b"
    r"|\b(thanks|thank you|ok thanks)\b"
    r"|مرحبا|مرحباً|اهلا|أهلا|أهلًا|السلام عليكم|مين انت|من انت|من أنت"
    r"|صباح الخير|مساء الخير|مسا الخير|تصبح على خير|نهارك سعيد|هلا|يا هلا|أهلين|اهلين"
    r"|كيفك|كيف حالك|كيف الأحوال|كيف الاحوال|كيف الأمور|كيف الامور|شو أخبارك|شو اخبارك|ايش أخبارك|ايش اخبارك|إيش أخبارك|إيش اخبارك"
    r"|شو بتعمل|شو ممكن تساعدني|بشو ممكن تساعدني|كيف بتساعدني|كيف ممكن تساعدني"
    r"|ماذا تستطيع|ماذا يمكنك|شو قدراتك|عرفني|عرفني عليك"
    r"|تشرفت|تشرفنا|شكرا|شكرًا|يسلمو|يعطيك العافية",
    re.IGNORECASE,
)

_TAX_GENERAL_RE = re.compile(
    r"\b(what is tax|explain tax|income tax basics|about tax|tax in general"
    r"|how does tax work|explain income tax)\b"
    r"|اشرح\s*لي\s+عن\s+الضريب[ةه]|اشرحلي\s+عن\s+الضريب[ةه]"
    r"|ما\s+هي\s+ضريب[ةه]\s+الدخل|ما\s+هي\s+الضريب[ةه]"
    r"|شو\s+هي\s+الضريب[ةه]|ايش\s+هي\s+الضريب[ةه]"
    r"|نبذة\s+عن\s+الضريب[ةه]|معلومات\s+عامة\s+عن\s+الضريب[ةه]"
    r"|شرح\s+ضريب[ةه]\s+الدخل|كيف\s+تعمل\s+الضريب[ةه]",
    re.IGNORECASE,
)

_TAX_LEGAL_RE = re.compile(
    r"\b(exemption|exemptions|deduct|deductible|deduction|deductions|bracket|rate|threshold|article|law|legal"
    r"|salary tax|income tax law|taxable income|filing|deadline|due date|return|invoice|receipt"
    r"|school fee|school fees|tuition|education expense|personal exemption|family exemption)\b"
    r"|إعفاء|اعفاء|إعفائ|اعفائ|الإعفاءات|الاعفاءات|خصم|خصومات|الخصومات|حسم|أحسم|احسم|ينحسم|تتحسم"
    r"|مدرسة|مدارس|أقساط|اقساط|قسط|تعليم|دراسة|أولادي|اولادي|ولادي"
    r"|شريحة|شرائح|نسبة|معدل|مادة|قانون|راتب|الدخل الخاضع"
    r"|تصريح|إقرار|اقرار|تقديم|موعد|آخر موعد|اخر موعد|إيمتى|ايمتى|متى|فاتورة|وصل|مكلف|مقيم|غير مقيم",
    re.IGNORECASE,
)

_TAX_TOPIC_RE = re.compile(
    r"\b(tax|income|deduct|deduction|exemption|law|legal|salary|filing|deadline|invoice|receipt|school fees|tuition)\b"
    r"|ضريبة|ضريبه|دخل|إعفاء|اعفاء|إعفائ|اعفائ|خصم|حسم|أحسم|احسم|قانون|راتب|تقديم|موعد|مدرسة|أقساط|اقساط|فاتورة|وصل",
    re.IGNORECASE,
)

_MEMORY_FOLLOWUP_RE = re.compile(
    r"\b(previous|earlier|before|remember|what did i|what have i|did i say"
    r"|my income|my salary|the amount|that amount|those details|the number)\b"
    r"|ذكرت|قلت|قبل|سابق|دخلي|راتبي|المبلغ|الرقم",
    re.IGNORECASE,
)

_ACCOUNT_RECALL_RE = re.compile(
    r"\b(what is|what's|what are|what does|what did|show|list|tell me|summarize|summary|which|how many|do i have)"
    r"[^\n?.!]{0,80}\b(my profile|my account|my deduction|my deductions"
    r"|my document|my documents|my uploads|my advisor|advisor report"
    r"|action plan|my refund|tax withheld|my exemption|my exemptions"
    r"|personal exemption|family exemption)\b"
    r"|ملفي|حسابي|خصوماتي|إعفائي|اعفائي|إعفاءاتي|اعفاءاتي|مستنداتي|وثائقي|تقرير المستشار|الخطة",
    re.IGNORECASE,
)

_CONTEXTUAL_CALC_FOLLOWUP_RE = re.compile(
    r"\b(what if|how about|what about|and if|if i|if i'm|if i am|same as"
    r"|instead|change it|add|remove|how much|my tax|tax due|tax liability)\b"
    r"|لو|اذا|إذا|ماذا لو|طيب|كم|ضريبتي|أدفع",
    re.IGNORECASE,
)

_CONTEXT_ACKNOWLEDGEMENT_RE = re.compile(
    r"^\s*(?:yes|yeah|yep|sure|ok|okay|please|do it|go ahead|calculate it"
    r"|نعم|اه|آه|اي|إي|أيوه|ايوه|تمام|أكيد|اكيد|يلا|بلش|احسبها|احسب)\s*[.!؟?]*\s*$",
    re.IGNORECASE,
)

_CALC_OFFER_CONTEXT_RE = re.compile(
    r"(?:would you like|do you want|shall i|should i|want me to|هل تود|هل تريد|بدك|بتحب|تحب|حابب|أقوم|اقوم)"
    r"[\s\S]{0,240}"
    r"(?:calculate|calculation|compute|tax due|tax liability|حساب|احسب|ضريبة)"
    r"|(?:calculate|calculation|deterministic tax|estimated tax|حساب ضريبة|ضريبة الدخل التقديرية)"
    r"[\s\S]{0,120}(?:\?|؟)",
    re.IGNORECASE,
)

_TAX_GENERAL_EXPANDED_QUERIES_AR = [
    "ضريبة الدخل الأردني القانون رقم 34 لسنة 2014",
    "شرح ضريبة الدخل في الأردن الإعفاءات الشرائح",
    "إعفاءات وشرائح ضريبة الدخل الأردن",
]

_TAX_GENERAL_EXPANDED_QUERIES_EN = [
    "Jordan income tax law number 34 of 2014",
    "Jordan income tax overview exemptions brackets",
    "Jordan income tax exemptions and brackets",
]


# ── Router ────────────────────────────────────────────────────────────────────

def _needs_calculation(question: str) -> bool:
    """True إذا السؤال يحتاج حساب ضريبي فعلي."""
    normalized = _normalize_digits(question)
    return bool(_CALC_TRIGGERS.search(normalized) and _NUMBER.search(normalized))


def _normalize_digits(text: str) -> str:
    return (text or "").translate(_ARABIC_INDIC_DIGITS)


def _amount_from_match(match: re.Match[str]) -> float:
    value = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").strip().lower()
    if suffix in _THOUSAND_SUFFIXES:
        value *= 1000
    return value


def _amount_candidates(pattern: re.Pattern[str], text: str) -> list[float]:
    return [_amount_from_match(match) for match in pattern.finditer(text)]


def _prefers_arabic(question: str, lang: str = "ar") -> bool:
    if _ARABIC_CHAR_RE.search(question):
        return True
    if re.search(r"[A-Za-z]", question):
        return False
    return lang.lower().startswith("ar")


def _answer_language_instruction(question: str, lang: str = "ar") -> str:
    if _prefers_arabic(question, lang):
        return (
            "أجب باللغة العربية. حافظ على أسلوب طبيعي وواضح، ولا تنتقل "
            "للإنجليزية إلا عند ذكر اسم نموذج أو مصطلح تقني كما هو."
        )
    return (
        "Answer in English. Do not switch to Arabic even if the retrieved "
        "sources or account context are Arabic; translate the relevant facts "
        "into English."
    )


def _is_direct_chat_question(question: str) -> bool:
    text = question.strip()
    if not text or len(text) > 240:
        return False
    if _TAX_LEGAL_RE.search(text):
        return False
    if _TAX_GENERAL_RE.search(text):
        return False
    return bool(_DIRECT_CHAT_RE.search(text))


def _is_tax_general_question(question: str) -> bool:
    text = question.strip()
    if not text:
        return False
    if _TAX_GENERAL_RE.search(text):
        return True
    return bool(_TAX_TOPIC_RE.search(text) and not _TAX_LEGAL_RE.search(text) and len(text) <= 100)


def _is_tax_legal_question(question: str) -> bool:
    text = question.strip()
    if not text:
        return False
    return bool(_TAX_LEGAL_RE.search(text) or (_TAX_TOPIC_RE.search(text) and not _is_tax_general_question(text)))


def classify_chat_intent(question: str, tax_inputs=None) -> ChatIntent:
    if tax_inputs is not None or _needs_calculation(question):
        return "tax_calculation"
    if _is_direct_chat_question(question):
        return "direct_chat"
    if _is_tax_general_question(question):
        return "tax_general"
    if _is_tax_legal_question(question):
        return "tax_legal_grounded"
    return "off_topic"


def _with_conversation_context(question: str, conversation_context: str | None) -> str:
    context = (conversation_context or "").strip()
    if not context:
        return question
    return (
        "Context available for this chat. It may include authenticated account "
        "data and previous session memory. Use it only when relevant, and treat "
        "the current user question as the task:\n"
        f"{context}\n\n"
        f"Current user question:\n{question}"
    )


def _intent_with_memory(
    question: str,
    conversation_context: str | None,
    tax_inputs=None,
) -> ChatIntent:
    if tax_inputs is not None:
        return "tax_calculation"
    if _is_direct_chat_question(question):
        return "direct_chat"
    if conversation_context and (
        _MEMORY_FOLLOWUP_RE.search(question) or _ACCOUNT_RECALL_RE.search(question)
    ):
        return "direct_chat"
    if conversation_context and _CONTEXT_ACKNOWLEDGEMENT_RE.match(question):
        if _CALC_OFFER_CONTEXT_RE.search(conversation_context):
            return "tax_calculation"
        return "direct_chat"
    if conversation_context and not _CONTEXTUAL_CALC_FOLLOWUP_RE.search(question):
        return classify_chat_intent(question, tax_inputs)
    routed_question = (
        _with_conversation_context(question, conversation_context)
        if conversation_context
        else question
    )
    return classify_chat_intent(routed_question, tax_inputs)


def _tax_general_no_source_answer(question: str, lang: str) -> str:
    if _prefers_arabic(question, lang):
        return TAX_GENERAL_NO_SOURCE_AR
    return TAX_GENERAL_NO_SOURCE_EN


def _legal_no_source_answer(question: str, lang: str) -> str:
    if _prefers_arabic(question, lang):
        return LEGAL_NO_SOURCE_AR
    return LEGAL_NO_SOURCE_EN


def _off_topic_answer(question: str, lang: str) -> str:
    if _prefers_arabic(question, lang):
        return OFF_TOPIC_AR
    return OFF_TOPIC_EN


def _retrieve_tax_general_context(
    question: str,
    top_k: int,
    source_type: Optional[str],
    lang: str,
    max_chars: int,
):
    expansions = (
        _TAX_GENERAL_EXPANDED_QUERIES_AR
        if _prefers_arabic(question, lang)
        else _TAX_GENERAL_EXPANDED_QUERIES_EN
    )
    queries = [question, *expansions]
    seen: set[str] = set()

    for query in queries:
        normalized = query.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        chunks, context = retrieve_with_context(
            normalized,
            top_k=top_k,
            source_type=source_type,
            lang=lang,
            max_chars=max_chars,
        )
        if chunks:
            return chunks, context
    return [], ""


def _extract_tax_inputs(question: str):
    """
    يحاول يستخرج TaxInput من النص.
    بسيط — يعتمد على الأرقام الموجودة في السؤال.
    للأسئلة المعقدة، اللانغراف هو المسؤول عن الاستخراج الكامل.
    """
    # relative imports تعمل دائماً بغض النظر عن كيفية تشغيل التطبيق
    from app.tax_engine import TaxInput
    from app.models import MaritalStatus

    # استخراج الأرقام — نفضل المبالغ القريبة من "دخل/راتب" أو العملة حتى لا
    # تختلط أرقام القانون/السنوات مع الدخل عند استخدام ذاكرة الجلسة.
    normalized = _normalize_digits(question)
    numbers = _amount_candidates(_INCOME_AMOUNT_RE, normalized)
    if not numbers:
        numbers = _amount_candidates(_CURRENCY_AMOUNT_RE, normalized)
    if not numbers:
        numbers = _amount_candidates(_NUMBER_AMOUNT_RE, normalized)
    gross_income = max(numbers) if numbers else 0.0

    # عدد المعالين — يشمل "معال / ابناء / أبناء / أولاد / أطفال"
    dep_match = re.search(
        r"(\d+)\s*(?:معال|أبناء|ابناء|أولاد|أطفال|أخوة|إخوة"
        r"|dependent|dependents|child|children|kid|kids)",
        normalized,
        re.IGNORECASE,
    )
    num_dependents = int(dep_match.group(1)) if dep_match else 0

    # الحالة الاجتماعية
    marital = (
        MaritalStatus.MARRIED
        if re.search(
            r"متزوج|متزوجة|زوج|زوجة|married|spouse|wife|husband",
            normalized,
            re.IGNORECASE,
        )
        else MaritalStatus.SINGLE
    )

    return TaxInput(
        gross_income=gross_income,
        marital_status=marital,
        num_dependents=num_dependents,
    )


def _format_tax_result(breakdown, question: str) -> str:
    """يحول TaxBreakdown لنص عربي واضح ومنظم."""
    lines = ["## نتيجة حساب ضريبة الدخل\n"]

    lines.append("**الدخل والإعفاءات:**")
    lines.append(f"- الدخل الإجمالي: {breakdown.gross_income:,.3f} دينار أردني")
    lines.append(f"- الإعفاء الشخصي: {breakdown.personal_exemption:,.3f} دينار أردني")
    if breakdown.family_exemption > 0:
        lines.append(f"- إعفاء الأسرة والمعالين: {breakdown.family_exemption:,.3f} دينار أردني")
    lines.append(f"- إجمالي الإعفاءات: {breakdown.total_exemptions:,.3f} دينار أردني")

    if breakdown.total_deductions > 0:
        lines.append("\n**الخصومات المقبولة:**")
        for cat, amount in breakdown.deductions_allowed.items():
            if amount > 0:
                lines.append(f"- {cat.value}: {amount:,.3f} دينار أردني")
        lines.append(f"- إجمالي الخصومات: {breakdown.total_deductions:,.3f} دينار أردني")

    lines.append(f"\n**الدخل الخاضع للضريبة: {breakdown.taxable_income:,.3f} دينار أردني**")

    if breakdown.bracket_breakdown:
        lines.append("\n**تفصيل الشرائح الضريبية:**")
        for b in breakdown.bracket_breakdown:
            upper = f"{b['to']:,.0f}" if b["to"] else "فما فوق"
            lines.append(
                f"- من {b['from']:,.0f} إلى {upper} دينار"
                f" بنسبة {b['rate'] * 100:.0f}%"
                f" ← ضريبة {b['tax']:,.3f} دينار"
            )

    lines.append(f"\n### الضريبة المستحقة: {breakdown.tax_liability:,.3f} دينار أردني")
    lines.append(f"- المعدل الفعلي: {breakdown.effective_rate * 100:.2f}%")
    lines.append(f"- أعلى شريحة ضريبية وصلها دخلك: {breakdown.marginal_rate * 100:.0f}%")

    if breakdown.tax_liability == 0:
        lines.append("\n✅ دخلك أقل من الحد الأدنى للضريبة — لا ضريبة مستحقة عليك.")

    return "\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────

def answer(
    question: str,
    top_k: int = 5,
    source_type: Optional[str] = None,
    lang: str = "ar",
    tax_inputs=None,   # TaxInput جاهز من LangGraph — يتجاوز الاستخراج التلقائي
    provider: Optional[str] = None,  # override settings.LLM_PROVIDER per-call
    model: Optional[str] = None,  # exact model selected by the UI
    max_tokens: Optional[int] = None,
    conversation_context: Optional[str] = None,
    intent_override: Optional[str] = None,  # route from the understanding layer; regex router is the fallback
) -> dict:
    """
    الراوتر الرئيسي:
      - إذا السؤال يحتاج حساب → tax_engine
      - غير ذلك               → RAG + LLM

    Returns:
        {
            "answer": str,
            "sources": [{"citation": str, "score": float}, ...],
            "provider": str,          # "tax_engine" | "anthropic" | ...
            "tax_breakdown": dict,    # موجود فقط إذا تم حساب ضريبي
        }
    """
    chosen_provider = (provider or LLM_PROVIDER).strip().lower()
    memory_question = _with_conversation_context(question, conversation_context)
    # Prefer the understanding layer's route; fall back to the regex router when it
    # is absent (LLM failed / disabled) so chat never hard-fails.
    if intent_override in _VALID_INTENTS:
        intent = intent_override
    else:
        intent = _intent_with_memory(question, conversation_context, tax_inputs)

    # ── مسار الحساب الضريبي ──────────────────────────────────────────────
    if intent == "tax_calculation":
        try:
            from app.tax_engine import calculate_tax, TaxInput
            inputs = tax_inputs or _extract_tax_inputs(memory_question)
            breakdown = calculate_tax(inputs)
            answer_text = _format_tax_result(breakdown, question)

            # أضف مرجع قانوني محدد — نبحث عن مواد الإعفاءات والشرائح
            legal_query = "الإعفاء الشخصي وإعفاء الأسرة والمعالين وشرائح ضريبة الدخل المادة 6 المادة 8"
            legal_chunks, _ = retrieve_with_context(legal_query, top_k=3, source_type="law", lang=lang)

            # فلتر: فقط الـ chunks ذات صلة عالية وتحتوي على نص عربي صحيح
            relevant = [
                c for c in legal_chunks
                if c.score >= 0.60
                and sum(1 for ch in c.text if "\u0600" <= ch <= "\u06FF") / max(len(c.text), 1) > 0.3
            ]

            if relevant:
                ref_lines = ["---", "**المستند القانوني (قانون ضريبة الدخل رقم 34 لسنة 2014):**"]
                for c in relevant:
                    ref_lines.append(f"- {c.citation}")
                answer_text += "\n\n" + "\n".join(ref_lines)

            return {
                "answer": answer_text,
                "sources": [{"citation": c.citation} for c in relevant] if relevant else [],
                "provider": "tax_engine",
                "model": None,
                "tax_breakdown": {
                    "gross_income": breakdown.gross_income,
                    "taxable_income": breakdown.taxable_income,
                    "tax_liability": breakdown.tax_liability,
                    "effective_rate": breakdown.effective_rate,
                    "marginal_rate": breakdown.marginal_rate,
                },
            }
        except Exception as exc:
            logger.warning("tax_engine failed (%s) — falling back to RAG+LLM", exc, exc_info=True)
            intent = "tax_legal_grounded"

    chosen_model = resolve_chat_model(chosen_provider, model)

    if intent == "direct_chat":
        llm_answer = _call_llm(
            chosen_provider,
            memory_question,
            chosen_model,
            system_prompt=DIRECT_CHAT_PROMPT,
            max_tokens=max_tokens,
        )
        return {
            "answer": llm_answer,
            "sources": [],
            "provider": chosen_provider,
            "model": chosen_model,
        }

    if intent == "off_topic":
        return {
            "answer": _off_topic_answer(question, lang),
            "sources": [],
            "provider": chosen_provider,
            "model": chosen_model,
        }

    # ── مسار RAG + LLM ───────────────────────────────────────────────────
    top_k = min(top_k, PROMPT_TOP_K_LIMITS.get(chosen_provider, top_k))
    max_context_chars = PROMPT_CHAR_LIMITS.get(chosen_provider, 18000)
    system_prompt = GENERAL_TAX_PROMPT if intent == "tax_general" else SYSTEM_PROMPT
    language_instruction = _answer_language_instruction(question, lang)
    question_label = "السؤال" if _prefers_arabic(question, lang) else "Question"
    prompt_wrapper = f"\n\n---\n{language_instruction}\n{question_label}: {memory_question}"
    context_max_chars = max(0, max_context_chars - len(prompt_wrapper) - len(system_prompt))
    retrieval_question = memory_question if conversation_context else question

    if intent == "tax_general":
        chunks, context = _retrieve_tax_general_context(
            retrieval_question,
            top_k=top_k,
            source_type=source_type,
            lang=lang,
            max_chars=context_max_chars,
        )
    else:
        chunks, context = retrieve_with_context(
            retrieval_question,
            top_k=top_k,
            source_type=source_type,
            lang=lang,
            max_chars=context_max_chars,
        )

    if not chunks:
        return {
            "answer": (
                _tax_general_no_source_answer(question, lang)
                if intent == "tax_general"
                else _legal_no_source_answer(question, lang)
            ),
            "sources": [],
            "provider": chosen_provider,
            "model": chosen_model,
        }

    user_message = f"{context}{prompt_wrapper}"

    if chosen_provider == "groq":
        try:
            llm_answer = _call_groq(
                user_message,
                chosen_model,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 413 or "Request too large" in str(exc) or "413" in str(exc):
                logger.warning("Groq prompt too large, retrying with smaller context: %s", exc)
                top_k = 1
                context_max_chars = max(1000, context_max_chars // 2)
                if intent == "tax_general":
                    chunks, context = _retrieve_tax_general_context(
                        retrieval_question,
                        top_k=top_k,
                        source_type=source_type,
                        lang=lang,
                        max_chars=context_max_chars,
                    )
                else:
                    chunks, context = retrieve_with_context(
                        retrieval_question,
                        top_k=top_k,
                        source_type=source_type,
                        lang=lang,
                        max_chars=context_max_chars,
                    )
                user_message = f"{context}{prompt_wrapper}"
                llm_answer = _call_groq(
                    user_message,
                    chosen_model,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                )
            else:
                raise
    else:
        llm_answer = _call_llm(
            chosen_provider,
            user_message,
            chosen_model,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

    return {
        "answer": llm_answer,
        "sources": [{"citation": c.citation, "score": c.score} for c in chunks],
        "provider": chosen_provider,
        "model": chosen_model,
    }


# ── Provider implementations ──────────────────────────────────────────────────

def _call_llm(
    provider: str,
    user_message: str,
    model: str,
    system_prompt: str = SYSTEM_PROMPT,
    max_tokens: int | None = None,
) -> str:
    if provider == "anthropic":
        return _call_anthropic(user_message, model, system_prompt, max_tokens)
    if provider == "openai":
        return _call_openai(user_message, model, system_prompt, max_tokens)
    if provider == "gemini":
        return _call_gemini(user_message, model, system_prompt, max_tokens)
    if provider == "groq":
        return _call_groq(
            user_message,
            model,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )
    raise ValueError(
        f"Unknown provider: {provider!r}. Choose: anthropic | openai | gemini | groq"
    )


def _call_anthropic(
    user_message: str,
    model: str,
    system_prompt: str = SYSTEM_PROMPT,
    max_tokens: int | None = None,
) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text(
        "anthropic", model=model, system=system_prompt, user=user_message,
        max_tokens=max_tokens or LLM_MAX_OUTPUT_TOKENS["anthropic"],
    )


def _call_openai(
    user_message: str,
    model: str,
    system_prompt: str = SYSTEM_PROMPT,
    max_tokens: int | None = None,
) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text(
        "openai", model=model, system=system_prompt, user=user_message,
        max_tokens=max_tokens or LLM_MAX_OUTPUT_TOKENS["openai"],
    )


def _call_groq(
    user_message: str,
    model: str,
    max_tokens: int | None = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text(
        "groq", model=model, system=system_prompt, user=user_message,
        max_tokens=max_tokens or LLM_MAX_OUTPUT_TOKENS["groq"],
    )


def _call_gemini(
    user_message: str,
    model: str,
    system_prompt: str = SYSTEM_PROMPT,
    max_tokens: int | None = None,
) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text(
        "gemini", model=model, system=system_prompt, user=user_message,
        max_tokens=max_tokens or LLM_MAX_OUTPUT_TOKENS["gemini"],
    )


# ── Title summarization (for chat history sidebar) ───────────────────────────

def _clean_title(raw: str) -> str:
    text = (raw or "").strip()
    # Strip surrounding quotes and trailing punctuation.
    text = text.strip('"').strip("'").strip("“”«»").strip()
    text = text.rstrip(".。!?؟").strip()
    return text[:120]


def _call_groq_simple(system: str, user: str, max_tokens: int = 32) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text("groq", model=settings.GROQ_TITLE_MODEL, system=system, user=user, max_tokens=max_tokens)


def _call_anthropic_simple(system: str, user: str, max_tokens: int = 32) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text("anthropic", model=settings.ANTHROPIC_TITLE_MODEL, system=system, user=user, max_tokens=max_tokens)


def _call_openai_simple(system: str, user: str, max_tokens: int = 32) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text("openai", model=settings.OPENAI_TITLE_MODEL, system=system, user=user, max_tokens=max_tokens)


def _call_gemini_simple(system: str, user: str, max_tokens: int = 32) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text("gemini", model=settings.GEMINI_TITLE_MODEL, system=system, user=user, max_tokens=max_tokens)


def summarize_title(
    question: str,
    answer: str,
    lang: str = "ar",
    provider: Optional[str] = None,
) -> str:
    """Generate a 3-5 word title from the first turn of a chat session.

    Tries (in order): groq → user-chosen provider → fallback to first 40 chars.
    Never raises — always returns a usable string.
    """
    system = TITLE_SYSTEM_PROMPT_AR if (lang or "ar").startswith("ar") else TITLE_SYSTEM_PROMPT_EN
    user = f"Q: {question[:400]}\nA: {answer[:600]}"

    candidates: list[str] = []
    if settings.GROQ_API_KEY:
        candidates.append("groq")
    chosen = (provider or LLM_PROVIDER).lower()
    if chosen not in candidates:
        candidates.append(chosen)

    for prov in candidates:
        try:
            if prov == "groq":
                raw = _call_groq_simple(system, user)
            elif prov == "anthropic":
                raw = _call_anthropic_simple(system, user)
            elif prov == "openai":
                raw = _call_openai_simple(system, user)
            elif prov == "gemini":
                raw = _call_gemini_simple(system, user)
            else:
                continue
            cleaned = _clean_title(raw)
            if cleaned:
                return cleaned
        except Exception as exc:  # noqa: BLE001
            logger.warning("title generation via %s failed: %s", prov, exc)
            continue

    return _clean_title(question[:40]) or "New chat"


# ── CLI quick-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "اذا كنت متزوج وعندي 4 ابناء ودخلي 15000 دينار، كم ضريبتي؟"
    result = answer(q)
    provider_label = {
        "tax_engine": "محرك الحساب الضريبي",
        "anthropic": "كلود (Anthropic)",
        "openai": "ChatGPT (OpenAI)",
        "groq": "المستشار القانوني",
        "gemini": "جيميناي (Google)",
    }.get(result["provider"], result["provider"])
    print(f"\n🔧 المصدر: {provider_label}")
    print(f"\n💬 الجواب:\n{result['answer']}")
    if result.get("sources"):
        print("\n📚 المراجع القانونية:")
        for s in result["sources"]:
            print(f"  - {s['citation']}")
