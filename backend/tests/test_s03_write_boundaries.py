"""Regression tests for untrusted writes and document processing retries."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import document_processing
from app.extraction.base import DeductionCategory, DocumentType, ExtractionResult
from app.main import app
from app.models.database import Deduction, Document, TaxProfile, User
from app.services.storage import get_storage


async def _user(client: AsyncClient, name: str) -> tuple[str, str]:
    username = f"s03-{name}@example.com"
    await client.post("/api/v1/auth/signup", json={
        "username": username, "password": "StrongPass123!", "name": name,
    })
    login = await client.post("/api/v1/auth/login", json={
        "username": username, "password": "StrongPass123!",
    })
    token = login.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _profile(client: AsyncClient, token: str) -> str:
    response = await client.post("/api/v1/tax-profiles/", json={
        "user_id": "00000000-0000-0000-0000-000000000000",
        "tax_year": 2026, "marital_status": "single", "num_dependents": 0,
    }, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_deduction_cannot_link_another_users_document(
    client: AsyncClient, db_session: AsyncSession,
):
    token_a, _ = await _user(client, "owner-a")
    _, user_b_id = await _user(client, "owner-b")
    profile_id = await _profile(client, token_a)
    foreign_doc = Document(user_id=uuid.UUID(user_b_id), file_path="foreign", original_filename="b.png", document_type="receipt")
    db_session.add(foreign_doc)
    await db_session.commit()

    base = {"tax_profile_id": profile_id, "category": "medical", "amount": "12"}
    blocked = await client.post("/api/v1/deductions/", json={**base, "document_id": str(foreign_doc.id)}, headers=_auth(token_a))
    assert blocked.status_code == 404
    created = await client.post("/api/v1/deductions/", json=base, headers=_auth(token_a))
    assert created.status_code == 201, created.text
    blocked_update = await client.put(
        f"/api/v1/deductions/{created.json()['id']}",
        json={"document_id": str(foreign_doc.id)}, headers=_auth(token_a),
    )
    assert blocked_update.status_code == 404
    current = await client.get(f"/api/v1/deductions/{created.json()['id']}", headers=_auth(token_a))
    assert current.json()["document_id"] is None

    own_doc = Document(user_id=uuid.UUID((await client.get("/api/v1/auth/me", headers=_auth(token_a))).json()["id"]), file_path="own", original_filename="a.png", document_type="receipt")
    db_session.add(own_doc)
    await db_session.commit()
    linked = await client.post("/api/v1/deductions/", json={**base, "document_id": str(own_doc.id)}, headers=_auth(token_a))
    assert linked.status_code == 201
    duplicate = await client.post("/api/v1/deductions/", json={**base, "document_id": str(own_doc.id)}, headers=_auth(token_a))
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_chat_updates_reject_invalid_values_without_writing(client: AsyncClient):
    token, _ = await _user(client, "validation")
    profile_id = await _profile(client, token)
    url = f"/api/v1/tax-profiles/{profile_id}/apply-chat-update"
    cases = [
        ("tax_profile", "num_dependents", "update", -1, None),
        ("tax_profile", "num_dependents", "update", 1.5, None),
        ("tax_profile", "marital_status", "update", "other", None),
        ("tax_profile", "marital_status", "update", None, None),
        ("income_source", "amount", "create", -10, None),
        ("income_source", "amount", "create", "NaN", None),
        ("income_source", "amount", "create", "Infinity", None),
        ("deduction", "amount", "create", 10, "unknown"),
    ]
    for entity, field, action, value, category in cases:
        response = await client.post(url, json={
            "entity": entity, "field": field, "action": action,
            "new_value": value, "category": category,
        }, headers=_auth(token))
        assert response.status_code == 422, (entity, field, value, response.text)

    profile = await client.get(f"/api/v1/tax-profiles/{profile_id}", headers=_auth(token))
    assert profile.json()["marital_status"] == "single"
    assert profile.json()["num_dependents"] == 0
    assert (await client.get("/api/v1/income-sources/", headers=_auth(token))).json() == []
    assert (await client.get("/api/v1/deductions/", headers=_auth(token))).json() == []

    direct_null = await client.put(
        f"/api/v1/tax-profiles/{profile_id}", json={"marital_status": None}, headers=_auth(token),
    )
    assert direct_null.status_code == 422
    direct_nan = await client.post("/api/v1/income-sources/", json={
        "tax_profile_id": profile_id, "type": "salary", "amount": "NaN",
    }, headers=_auth(token))
    assert direct_nan.status_code == 422


@pytest.mark.asyncio
async def test_avatar_and_voice_reject_untrusted_media_before_provider(
    client: AsyncClient, monkeypatch,
):
    token, _ = await _user(client, "media")
    app.dependency_overrides[get_storage] = lambda: object()
    try:
        avatar = await client.post("/api/v1/users/me/avatar", files={
            "file": ("avatar.png", b"not an image", "image/png"),
        }, headers=_auth(token))
        assert avatar.status_code == 400
    finally:
        app.dependency_overrides.pop(get_storage, None)

    from app.voice import transcription

    monkeypatch.setattr(transcription, "GeminiClipTranscriber", lambda: pytest.fail("provider initialized"))
    voice = await client.post("/api/v1/voice/transcribe", json={
        "audio_b64": "AAAA", "mime_type": "audio/webm",
    }, headers=_auth(token))
    assert voice.status_code == 400
    spoofed_wav = await client.post("/api/v1/voice/transcribe", json={
        "audio_b64": "AAAA", "mime_type": "audio/wav",
    }, headers=_auth(token))
    assert spoofed_wav.status_code == 400


@pytest.mark.asyncio
async def test_processing_requires_confirmation_and_retry_preserves_link(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,
):
    token, user_id = await _user(client, "processing")
    user = await db_session.get(User, uuid.UUID(user_id))
    user.subscription_tier = "Pro"
    await db_session.commit()
    profile_id = await _profile(client, token)
    profile = await db_session.get(TaxProfile, uuid.UUID(profile_id))
    original_version = profile.version
    docs = [Document(user_id=uuid.UUID(user_id), file_path=str(i), original_filename=f"{i}.png", document_type="receipt") for i in range(2)]
    db_session.add_all(docs)
    await db_session.commit()

    class Storage:
        async def download_file(self, file_path):
            return b"\x89PNG\r\n\x1a\nimage"

    app.dependency_overrides[get_storage] = lambda: Storage()
    confidence = 0.95

    async def extract(_data, *, mime_type):
        return ExtractionResult(amount=24.5, category=DeductionCategory.MEDICAL, document_type=DocumentType.RECEIPT, confidence=confidence)

    monkeypatch.setattr(document_processing, "extract_document", extract)
    try:
        url = f"/api/v1/documents/{docs[0].id}/process?tax_profile_id={profile_id}"
        first = await client.post(url, headers=_auth(token))
        second = await client.post(url, headers=_auth(token))
        assert first.status_code == second.status_code == 200
        assert first.json()["deduction_id"] is None
        assert second.json()["deduction_id"] is None
        assert first.json()["extracted_data"]["awaiting_confirmation"] is True
        assert first.json()["extracted_data"]["needs_review"] is False
        assert (await db_session.execute(select(Deduction))).scalars().all() == []
        await db_session.refresh(profile)
        assert profile.version == original_version

        confidence = 0.6
        weak = await client.post(
            f"/api/v1/documents/{docs[1].id}/process?tax_profile_id={profile_id}",
            headers=_auth(token),
        )
        assert weak.status_code == 200, weak.text
        assert weak.json()["deduction_id"] is None
        assert weak.json()["extracted_data"]["needs_review"] is True
        assert weak.json()["extracted_data"]["awaiting_confirmation"] is True

        confirmed = await client.post(
            "/api/v1/deductions/",
            json={
                "tax_profile_id": profile_id,
                "category": "medical",
                "amount": "24.5",
                "document_id": str(docs[0].id),
            },
            headers={**_auth(token), "If-Match": str(original_version)},
        )
        assert confirmed.status_code == 201, confirmed.text
        retried = await client.post(url, headers=_auth(token))
        assert retried.status_code == 200, retried.text
        assert retried.json()["deduction_id"] == confirmed.json()["id"]
        assert retried.json()["extracted_data"]["awaiting_confirmation"] is False
        rows = (await db_session.execute(select(Deduction))).scalars().all()
        assert len(rows) == 1
        await db_session.refresh(profile)
        assert profile.version == original_version + 1
    finally:
        app.dependency_overrides.pop(get_storage, None)
