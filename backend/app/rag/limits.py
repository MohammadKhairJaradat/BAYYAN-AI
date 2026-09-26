"""Per-provider runtime guardrails for chat retrieval and LLM calls.

These caps reflect each provider's actual API limits (input-token budget,
free-tier constraints, output token defaults). They are NOT user-tunable
preferences — bumping a value upward without checking the provider's docs
will produce 400 errors. Update alongside any model swap or provider change.

Intentionally NOT exposed via .env / pydantic settings: a developer
adjusting these should also be touching the provider integration in qa.py.
"""

PROMPT_CHAR_LIMITS = {
    "groq": 6000,
    "openai": 22000,
    "anthropic": 22000,
    "gemini": 22000,
}

PROMPT_TOP_K_LIMITS = {
    "groq": 2,
    "openai": 5,
    "anthropic": 5,
    "gemini": 5,
}

LLM_MAX_OUTPUT_TOKENS = {
    "groq": 512,
    "openai": 1024,
    "anthropic": 1024,
    "gemini": 1024,
}
