from datetime import datetime, timezone

from app.auth.tier_limits import (
    current_usage_month,
    get_tier_limits,
    is_model_allowed,
)


def test_tier_model_access_is_additive():
    assert is_model_allowed("Basic", "groq", "llama-3.1-8b-instant")
    assert not is_model_allowed("Basic", "openai", "gpt-4o")

    assert is_model_allowed("Pro", "groq", "llama-3.1-8b-instant")
    assert is_model_allowed("Pro", "gemini", "gemini-2.5-flash")
    assert is_model_allowed("Pro", "openai", "gpt-4o")
    assert not is_model_allowed("Pro", "openai", "gpt-5.4")
    assert not is_model_allowed("Pro", "gemini", "gemini-2.5-pro")

    assert is_model_allowed("Premium", "openai", "gpt-5.4")
    assert is_model_allowed("Premium", "anthropic", "claude-opus-4-7")
    assert is_model_allowed("Premium", "gemini", "gemini-2.5-pro")


def test_tier_limits_match_subscription_design():
    basic = get_tier_limits("Basic")
    pro = get_tier_limits("Pro")
    premium = get_tier_limits("Premium")

    assert basic.max_tokens == 1024
    assert basic.max_messages_per_month == 60
    assert basic.max_docs_per_month == 10
    assert basic.max_extractions_per_month == 10

    assert pro.max_tokens == 2048
    assert pro.max_messages_per_month == 200
    assert pro.max_docs_per_month == 50
    assert pro.max_extractions_per_month == 50

    assert premium.max_tokens == 4096
    assert premium.max_messages_per_month == 500
    assert premium.max_docs_per_month == 150
    assert premium.max_extractions_per_month == 150


def test_current_usage_month_uses_jordan_calendar():
    utc_time = datetime(2026, 4, 30, 22, 30, tzinfo=timezone.utc)

    assert current_usage_month(utc_time).isoformat() == "2026-05-01"
