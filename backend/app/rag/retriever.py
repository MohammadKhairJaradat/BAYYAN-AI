"""
retriever.py — High-level RAG retrieval interface.

Used by LangGraph advisor nodes.
Responsibilities:
- Retrieve relevant legal chunks
- Build user-friendly context
- Format final answer for non-specialist users
"""

from __future__ import annotations

import logging
from typing import Optional, List, Tuple, Dict

from .vector_store import RetrievedChunk, VectorStore

logger = logging.getLogger(__name__)

_store: Optional[VectorStore] = None


# ---------------------------------------------------------------------
# Vector store access
# ---------------------------------------------------------------------
def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


# ---------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------
def retrieve(
    question: str,
    top_k: int = 5,
    source_type: Optional[str] = None,
) -> List[RetrievedChunk]:
    store = get_store()
    chunks = store.query(
        question,
        top_k=top_k,
        source_type_filter=source_type,
    )

    logger.debug(
        "Retrieved %d chunks for question: %.60s...",
        len(chunks),
        question,
    )
    return chunks


# ---------------------------------------------------------------------
# Context block (for LLM grounding)
# ---------------------------------------------------------------------
def build_context_block(
    chunks: List[RetrievedChunk],
    lang: str = "ar",
    max_chars: Optional[int] = None,
) -> str:
    if not chunks:
        return ""

    lines: List[str] = []
    total_chars = 0

    if lang == "ar":
        lines.append("### 📚 المصادر القانونية ذات الصلة\n")
        relevance_label = "درجة الصلة"
    else:
        lines.append("### Relevant Legal Sources\n")
        relevance_label = "Relevance"

    for i, chunk in enumerate(chunks, start=1):
        entry = (
            f"[{i}] **{chunk.citation}** "
            f"({relevance_label}: {chunk.score:.2f})\n"
            f"{chunk.text}\n"
        )

        if max_chars and total_chars + len(entry) > max_chars:
            break

        lines.append(entry)
        total_chars += len(entry)

    return "\n".join(lines)


# ---------------------------------------------------------------------
# ✅ FINAL USER-FRIENDLY ANSWER (THE IMPORTANT PART)
# ---------------------------------------------------------------------
def format_income_tax_answer(
    *,
    income: float,
    personal_exemption: float,
    family_exemption: float,
    taxable_income: float,
    brackets: List[Dict],
    total_tax: float,
    effective_rate: float,
    top_bracket_rate: float,
    legal_source: str,
    references: List[str],
) -> str:
    """
    Produce a clear, educational answer for users who know nothing about tax.
    """

    lines: List[str] = []

    lines.append("🔧 **المصدر:** محرك الحساب الضريبي\n")
    lines.append("💬 **الجواب:**")
    lines.append("## ✅ نتيجة حساب ضريبة الدخل\n")

    # Income & exemptions
    lines.append("### الدخل والإعفاءات:")
    lines.append(f"- الدخل الإجمالي: {income:,.3f} دينار أردني")
    lines.append(f"- الإعفاء الشخصي: {personal_exemption:,.3f} دينار أردني")
    lines.append(f"- إعفاء الأسرة والمعالين: {family_exemption:,.3f} دينار أردني")
    lines.append(
        f"- **إجمالي الإعفاءات:** "
        f"{(personal_exemption + family_exemption):,.3f} دينار أردني\n"
    )

    lines.append(
        f"**الدخل الخاضع للضريبة:** {taxable_income:,.3f} دينار أردني\n"
    )

    # Brackets
    lines.append("### تفصيل الشرائح الضريبية:")
    for b in brackets:
        lines.append(
            f"- من {b['from']:,.0f} إلى {b['to']:,.0f} دينار "
            f"بنسبة {b['rate']}% "
            f"← ضريبة {b['tax']:,.3f} دينار"
        )

    # Final result
    lines.append("\n### ✅ الضريبة المستحقة:")
    lines.append(f"**{total_tax:,.3f} دينار أردني**")
    lines.append(f"- المعدل الفعلي: {effective_rate:.2f}%")
    lines.append(f"- أعلى شريحة ضريبية وصلها دخلك: {top_bracket_rate}%")

    # Simple takeaway
    lines.append(
        f"\n🟢 **ببساطة:** ستدفع **{total_tax:,.0f} دينار أردني فقط** كضريبة دخل."
    )

    # Legal references
    lines.append("\n---")
    lines.append(f"**المستند القانوني ({legal_source}):**")
    for ref in references:
        lines.append(f"- {ref}")

    return "\n".join(lines)


# ---------------------------------------------------------------------
# Combined helper
# ---------------------------------------------------------------------
def retrieve_with_context(
    question: str,
    top_k: int = 5,
    source_type: Optional[str] = None,
    lang: str = "ar",
    max_chars: Optional[int] = None,
) -> Tuple[List[RetrievedChunk], str]:
    chunks = retrieve(
        question=question,
        top_k=top_k,
        source_type=source_type,
    )
    context = build_context_block(
        chunks=chunks,
        lang=lang,
        max_chars=max_chars,
    )
    return chunks, context