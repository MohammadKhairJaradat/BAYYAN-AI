from httpx import AsyncClient

from app.auth.tier_limits import TIER_LIMITS, TIER_ORDER, allowed_models_payload
from app.config import settings


async def test_public_capabilities_match_enforced_tier_limits(client: AsyncClient):
    response = await client.get("/api/v1/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["product"] == "BAYYAN"
    assert body["tier_changes"] == "admin_only"
    assert body["official_filing"] is False
    assert body["legal_corpus"] == "demo"
    assert set(body["ai"]) == {"configured_providers", "document_extraction", "advisor", "voice"}
    assert [tier["name"] for tier in body["tiers"]] == list(TIER_ORDER)
    for tier in body["tiers"]:
        limits = TIER_LIMITS[tier["name"]]
        assert tier["max_messages_per_month"] == limits.max_messages_per_month
        assert tier["max_docs_per_month"] == limits.max_docs_per_month
        assert tier["max_tokens"] == limits.max_tokens
        assert tier["allowed_models"] == allowed_models_payload(tier["name"])
        assert "price" not in tier


async def test_capabilities_report_ai_readiness_without_exposing_keys(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-for-test")
    monkeypatch.setattr(settings, "GOOGLE_AI_API_KEY", "")
    monkeypatch.setattr(settings, "ADVISOR_LLM_PROVIDER", "gemini")
    response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    ai = response.json()["ai"]
    assert "gemini" in ai["configured_providers"]
    assert ai["document_extraction"] is True
    assert ai["advisor"] is True
    assert ai["voice"] is True
    assert "fake-for-test" not in response.text
