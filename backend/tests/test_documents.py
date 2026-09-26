import uuid
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tier_limits import current_usage_month
from app.main import app
from app.models.database import MonthlyUsage, User
from app.services.storage import get_storage

SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
UPLOAD_URL = "/api/v1/documents/upload"
LIST_URL = "/api/v1/documents/"

USER_A = {
    "username": "alice@example.com",
    "password": "StrongPass123!",
    "name": "Alice",
}
USER_B = {
    "username": "bob@example.com",
    "password": "StrongPass123!",
    "name": "Bob",
}


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def ensure_bucket(self) -> None:  # pragma: no cover - not exercised
        return None

    async def upload_file(
        self, file_data: bytes, filename: str, user_id: uuid.UUID
    ) -> str:
        key = f"{user_id}/{uuid.uuid4().hex}_{filename}"
        self.objects[key] = file_data
        return key

    async def download_file(self, file_path: str) -> bytes:
        return self.objects[file_path]

    async def delete_file(self, file_path: str) -> bool:
        self.deleted.append(file_path)
        self.objects.pop(file_path, None)
        return True


@pytest.fixture
def fake_storage() -> FakeStorage:
    fake = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_storage, None)


async def _signup_and_login(client: AsyncClient, user: dict) -> str:
    await client.post(SIGNUP_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"username": user["username"], "password": user["password"]}
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _set_tier(db_session: AsyncSession, username: str, tier: str) -> None:
    """Direct-write tier on the test DB. The self-serve POST /me/tier route is
    gone; tier changes are admin-only in production. Tests own their state, so
    we just flip the column."""
    user = (
        await db_session.execute(select(User).where(User.username == username))
    ).scalar_one()
    user.subscription_tier = tier
    await db_session.commit()


async def _upload(
    client: AsyncClient,
    token: str,
    *,
    filename: str = "receipt.png",
    content: bytes = b"\x89PNG\r\n\x1a\nfakepngbody",
    document_type: str = "receipt",
    content_type: str = "image/png",
):
    return await client.post(
        UPLOAD_URL,
        headers=_auth(token),
        files={"file": (filename, content, content_type)},
        data={"document_type": document_type},
    )


@pytest.mark.asyncio
async def test_upload_creates_db_record(
    client: AsyncClient, fake_storage: FakeStorage, db_session: AsyncSession
):
    token = await _signup_and_login(client, USER_A)
    await _set_tier(db_session, USER_A["username"], "Pro")
    resp = await _upload(client, token)

    assert resp.status_code == 201
    data = resp.json()
    assert data["processing_status"] == "pending"
    assert data["document_type"] == "receipt"
    assert data["original_filename"] == "receipt.png"
    assert data["file_path"] in fake_storage.objects

    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()
    from tests.conftest import TestSessionFactory

    async with TestSessionFactory() as db:
        result = await db.execute(
            select(MonthlyUsage).where(MonthlyUsage.user_id == UUID(me["id"]))
        )
        usage = result.scalar_one()
        assert usage.doc_count == 1

    get_resp = await client.get(
        f"/api/v1/documents/{data['id']}", headers=_auth(token)
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == data["id"]


@pytest.mark.asyncio
async def test_upload_rejects_invalid_file_type(
    client: AsyncClient, fake_storage: FakeStorage
):
    token = await _signup_and_login(client, USER_A)
    resp = await _upload(
        client,
        token,
        filename="malware.exe",
        content=b"MZfakebinary",
        content_type="application/octet-stream",
    )
    assert resp.status_code == 400
    assert fake_storage.objects == {}


@pytest.mark.asyncio
async def test_upload_rejects_mismatched_signature_and_mime_without_using_quota(
    client: AsyncClient, fake_storage: FakeStorage, db_session: AsyncSession,
):
    token = await _signup_and_login(client, USER_A)
    await _set_tier(db_session, USER_A["username"], "Pro")
    bad_signature = await _upload(client, token, content=b"<script>not a png</script>")
    assert bad_signature.status_code == 400
    bad_mime = await _upload(client, token, content_type="application/pdf")
    assert bad_mime.status_code == 400
    assert fake_storage.objects == {}
    good = await _upload(client, token)
    assert good.status_code == 201
    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()
    usage = (await db_session.execute(
        select(MonthlyUsage).where(MonthlyUsage.user_id == UUID(me["id"]))
    )).scalar_one()
    assert usage.doc_count == 1


@pytest.mark.asyncio
async def test_basic_upload_can_start_document_workflow(
    client: AsyncClient, fake_storage: FakeStorage
):
    token = await _signup_and_login(client, USER_A)
    resp = await _upload(client, token)

    assert resp.status_code == 201
    assert len(fake_storage.objects) == 1


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(
    client: AsyncClient, fake_storage: FakeStorage, db_session: AsyncSession
):
    token = await _signup_and_login(client, USER_A)
    await _set_tier(db_session, USER_A["username"], "Pro")
    oversized = b"\x00" * (11 * 1024 * 1024)
    resp = await _upload(client, token, content=oversized)
    assert resp.status_code == 413
    assert fake_storage.objects == {}


@pytest.mark.asyncio
async def test_upload_rejects_pro_user_at_doc_quota(
    client: AsyncClient, fake_storage: FakeStorage, db_session: AsyncSession
):
    token = await _signup_and_login(client, USER_A)
    await _set_tier(db_session, USER_A["username"], "Pro")
    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()

    from tests.conftest import TestSessionFactory

    async with TestSessionFactory() as db:
        db.add(
            MonthlyUsage(
                user_id=UUID(me["id"]),
                usage_month=current_usage_month(),
                message_count=0,
                doc_count=50,
            )
        )
        await db.commit()

    resp = await _upload(client, token)

    assert resp.status_code == 429
    assert "Monthly document upload quota reached" in resp.json()["detail"]
    assert fake_storage.objects == {}


@pytest.mark.asyncio
async def test_list_returns_only_current_users_documents(
    client: AsyncClient, fake_storage: FakeStorage, db_session: AsyncSession
):
    token_a = await _signup_and_login(client, USER_A)
    await _set_tier(db_session, USER_A["username"], "Pro")
    await _upload(client, token_a)

    token_b = await _signup_and_login(client, USER_B)
    list_b = await client.get(LIST_URL, headers=_auth(token_b))
    assert list_b.status_code == 200
    assert list_b.json() == []

    list_a = await client.get(LIST_URL, headers=_auth(token_a))
    assert list_a.status_code == 200
    assert len(list_a.json()) == 1


@pytest.mark.asyncio
async def test_delete_removes_db_and_storage(
    client: AsyncClient, fake_storage: FakeStorage, db_session: AsyncSession
):
    token = await _signup_and_login(client, USER_A)
    await _set_tier(db_session, USER_A["username"], "Pro")
    upload_resp = await _upload(client, token)
    doc_id = upload_resp.json()["id"]
    file_path = upload_resp.json()["file_path"]

    del_resp = await client.delete(
        f"/api/v1/documents/{doc_id}", headers=_auth(token)
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/documents/{doc_id}", headers=_auth(token)
    )
    assert get_resp.status_code == 404

    assert file_path in fake_storage.deleted
    assert file_path not in fake_storage.objects


@pytest.mark.asyncio
async def test_list_and_get_documents_report_has_linked_deduction_truthfully(
    client: AsyncClient, fake_storage: FakeStorage, db_session: AsyncSession
):
    tax_profiles_url = "/api/v1/tax-profiles/"
    deductions_url = "/api/v1/deductions/"

    token_a = await _signup_and_login(client, USER_A)
    await _set_tier(db_session, USER_A["username"], "Pro")

    # User A uploads doc1 and doc2
    doc1_resp = await _upload(client, token_a, filename="receipt1.png")
    doc2_resp = await _upload(client, token_a, filename="receipt2.png")
    doc1_id = doc1_resp.json()["id"]
    doc2_id = doc2_resp.json()["id"]

    # Before deduction is created, both report has_linked_deduction = False
    list_a_init = (await client.get(LIST_URL, headers=_auth(token_a))).json()
    assert len(list_a_init) == 2
    assert all(d["has_linked_deduction"] is False for d in list_a_init)

    # User A creates a tax profile and links a deduction to doc1
    prof_a_resp = await client.post(
        tax_profiles_url,
        json={
            "user_id": "00000000-0000-0000-0000-000000000000",
            "tax_year": 2026,
            "marital_status": "single",
            "num_dependents": 0,
        },
        headers=_auth(token_a),
    )
    assert prof_a_resp.status_code == 201, prof_a_resp.text
    prof_a = prof_a_resp.json()

    ded_a_resp = await client.post(
        deductions_url,
        json={
            "tax_profile_id": prof_a["id"],
            "category": "medical",
            "amount": "250",
            "document_id": doc1_id,
        },
        headers=_auth(token_a),
    )
    assert ded_a_resp.status_code == 201, ded_a_resp.text
    ded_a = ded_a_resp.json()
    assert ded_a["document_id"] == doc1_id

    # User B uploads doc3 and links it to User B's profile
    token_b = await _signup_and_login(client, USER_B)
    await _set_tier(db_session, USER_B["username"], "Pro")
    doc3_resp = await _upload(client, token_b, filename="receipt3.png")
    doc3_id = doc3_resp.json()["id"]

    prof_b_resp = await client.post(
        tax_profiles_url,
        json={
            "user_id": "00000000-0000-0000-0000-000000000000",
            "tax_year": 2026,
            "marital_status": "single",
            "num_dependents": 0,
        },
        headers=_auth(token_b),
    )
    assert prof_b_resp.status_code == 201, prof_b_resp.text
    prof_b = prof_b_resp.json()

    ded_b_resp = await client.post(
        deductions_url,
        json={
            "tax_profile_id": prof_b["id"],
            "category": "education",
            "amount": "500",
            "document_id": doc3_id,
        },
        headers=_auth(token_b),
    )
    assert ded_b_resp.status_code == 201, ded_b_resp.text

    # Verify User A's list and get responses
    list_a = (await client.get(LIST_URL, headers=_auth(token_a))).json()
    doc_map_a = {d["id"]: d for d in list_a}
    assert doc_map_a[doc1_id]["has_linked_deduction"] is True
    assert doc_map_a[doc2_id]["has_linked_deduction"] is False

    get_a1 = (await client.get(f"/api/v1/documents/{doc1_id}", headers=_auth(token_a))).json()
    assert get_a1["has_linked_deduction"] is True

    get_a2 = (await client.get(f"/api/v1/documents/{doc2_id}", headers=_auth(token_a))).json()
    assert get_a2["has_linked_deduction"] is False

    # Verify User B's list and get responses
    list_b = (await client.get(LIST_URL, headers=_auth(token_b))).json()
    assert len(list_b) == 1
    assert list_b[0]["id"] == doc3_id
    assert list_b[0]["has_linked_deduction"] is True

    get_b3 = (await client.get(f"/api/v1/documents/{doc3_id}", headers=_auth(token_b))).json()
    assert get_b3["has_linked_deduction"] is True
