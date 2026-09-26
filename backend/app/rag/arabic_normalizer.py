"""
arabic_normalizer.py — Arabic text normalization for RAG pipeline.

IMPORTANT: We keep two versions of every text:
  - original: displayed to the user as-is (preserve legal text exactly)
  - normalized: used only for embedding/search (improves recall)

Why normalization matters for Arabic legal text:
  - Same word written differently (أ/ا/إ) → miss retrievals
  - Tashkeel (harakat) differ between sources
  - Tatweel (kashida) appears in some PDFs
  - Extra whitespace from PDF extraction
"""

from __future__ import annotations

import re
import unicodedata


# ── Character mappings ────────────────────────────────────────────────────────

# Hamza normalization: unify all alef forms → bare alef ا
_ALEF_MAP = str.maketrans({
    "أ": "ا",  # alef with hamza above
    "إ": "ا",  # alef with hamza below
    "آ": "ا",  # alef with madda
    "ٱ": "ا",  # alef wasla
})

# Teh marbuta → heh (helps match e.g. ضريبة vs ضريبه)
# NOTE: disabled by default for legal text — can cause false matches
# _TEH_MARBUTA = str.maketrans({"ة": "ه"})

# Yeh normalization: unify alef maqsura ى → yeh ي
_YEH_MAP = str.maketrans({
    "ى": "ي",   # alef maqsura → yeh
    "ئ": "ي",   # yeh with hamza → yeh
})

# Waw with hamza → waw
_WAW_MAP = str.maketrans({
    "ؤ": "و",
})

# Arabic punctuation → ASCII equivalents (for tokenization)
_PUNCT_MAP = str.maketrans({
    "،": ",",
    "؛": ";",
    "؟": "?",
    "«": '"',
    "»": '"',
})

# Tashkeel (harakat) Unicode range
_TASHKEEL = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670]")

# Tatweel (kashida stretcher)
_TATWEEL = re.compile(r"\u0640+")

# Extra whitespace (including non-breaking space, zero-width etc.)
_EXTRA_SPACE = re.compile(r"[\s\u00A0\u200B\u200C\u200D\uFEFF]+")

# Arabic-Indic digits → Western Arabic digits
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


# ── Core normalization functions ──────────────────────────────────────────────

def remove_tashkeel(text: str) -> str:
    """Remove all Arabic diacritics (harakat/tashkeel)."""
    return _TASHKEEL.sub("", text)


def remove_tatweel(text: str) -> str:
    """Remove kashida (Arabic letter stretcher ـ)."""
    return _TATWEEL.sub("", text)


def normalize_alef(text: str) -> str:
    """Unify all alef variants → bare alef ا."""
    return text.translate(_ALEF_MAP)


def normalize_yeh(text: str) -> str:
    """Unify alef maqsura ى → yeh ي."""
    return text.translate(_YEH_MAP)


def normalize_waw(text: str) -> str:
    """Unify waw with hamza ؤ → waw و."""
    return text.translate(_WAW_MAP)


def normalize_arabic_digits(text: str) -> str:
    """Convert Arabic-Indic digits (٠١٢...) to Western Arabic digits (012...)."""
    return text.translate(_ARABIC_INDIC)


def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace variants to single space and strip edges."""
    return _EXTRA_SPACE.sub(" ", text).strip()


def normalize_unicode(text: str) -> str:
    """Apply Unicode NFC normalization."""
    return unicodedata.normalize("NFC", text)


# ── Main public API ───────────────────────────────────────────────────────────

def normalize_for_search(text: str) -> str:
    """
    Full normalization pipeline for SEARCH/EMBEDDING only.
    Never show this to the user — use original text for display.

    Pipeline:
        1. Unicode NFC
        2. Remove tashkeel
        3. Remove tatweel
        4. Normalize alef variants → ا
        5. Normalize yeh variants → ي
        6. Normalize waw variants → و
        7. Normalize Arabic-Indic digits
        8. Collapse whitespace
    """
    text = normalize_unicode(text)
    text = remove_tashkeel(text)
    text = remove_tatweel(text)
    text = normalize_alef(text)
    text = normalize_yeh(text)
    text = normalize_waw(text)
    text = normalize_arabic_digits(text)
    text = normalize_whitespace(text)
    return text


def normalize_query(query: str) -> str:
    """
    Normalize a user query before embedding.
    Same pipeline as normalize_for_search — must stay identical
    so query and document vectors are in the same space.
    """
    return normalize_for_search(query)


def normalize_for_display(text: str) -> str:
    """
    Light normalization for display: only fix whitespace and unicode.
    Preserves the original legal text (tashkeel, alef forms, etc.).
    """
    text = normalize_unicode(text)
    text = normalize_whitespace(text)
    return text


# ── Utility ───────────────────────────────────────────────────────────────────

def is_arabic(text: str, threshold: float = 0.3) -> bool:
    """Return True if >threshold fraction of characters are Arabic."""
    if not text:
        return False
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    return arabic_chars / len(text) > threshold


def detect_language(text: str) -> str:
    """Simple language detection: 'ar', 'en', or 'mixed'."""
    if not text:
        return "en"
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    latin_chars = sum(1 for c in text if "a" <= c.lower() <= "z")
    total = len(text.replace(" ", ""))
    if total == 0:
        return "en"
    ar_ratio = arabic_chars / total
    en_ratio = latin_chars / total
    if ar_ratio > 0.6:
        return "ar"
    if en_ratio > 0.6:
        return "en"
    return "mixed"


# ── CLI smoke test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    samples = [
        "مَا هِيَ الإعْفَاءَاتُ الشَّخْصِيَّة؟",       # tashkeel
        "قـانـون ضـريـبـة الـدخـل",                    # tatweel
        "أحكام إعفاء الأسرة",                           # alef variants
        "الدخل الخاضع للضريبة",                         # standard
        "What are the deductions حسب القانون؟",         # mixed
        "دخلى السنوى ١٨٠٠٠ دينار",                     # Arabic-Indic digits + alef maqsura
    ]

    print("Arabic Normalizer — smoke test\n" + "=" * 45)
    for s in samples:
        normalized = normalize_for_search(s)
        lang = detect_language(s)
        print(f"  Input   : {s}")
        print(f"  Norm    : {normalized}")
        print(f"  Lang    : {lang}")
        print()
