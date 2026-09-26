import pytest

from app.auth.dependencies import decode_access_token
from app.auth.security import create_access_token, create_refresh_token


def test_decode_access_token_accepts_access_token():
    token = create_access_token({"sub": "00000000-0000-0000-0000-000000000001"})

    payload = decode_access_token(token)

    assert payload["sub"] == "00000000-0000-0000-0000-000000000001"
    assert payload["type"] == "access"


def test_decode_access_token_rejects_refresh_token():
    token = create_refresh_token({"sub": "00000000-0000-0000-0000-000000000001"})

    with pytest.raises(ValueError):
        decode_access_token(token)
