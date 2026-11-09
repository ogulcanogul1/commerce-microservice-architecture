import json
from typing import Any
import uuid
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.core.security import get_request_context, require_gateway_secret
from app.main import app


@pytest.mark.anyio
async def test_get_request_context_valid_uuid_and_normalization() -> None:
    # Büyük harfli geçerli UUID verildiğinde küçük harfe ve standart biçime normalize edilmeli
    raw_uuid = "123E4567-E89B-12D3-A456-426614174000"
    ctx = await get_request_context(x_user_id=raw_uuid, x_correlation_id="corr-123")

    assert ctx.user_id == raw_uuid.lower()
    assert ctx.correlation_id == "corr-123"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_user_id",
    [
        None,
        "",
        "   ",
        "abc",
        "123",
        "1; DROP TABLE users;",
        "not-a-uuid-at-all",
    ],
)
async def test_get_request_context_invalid_or_missing_raises_401(
    invalid_user_id: str | None,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_request_context(x_user_id=invalid_user_id)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Kimlik doğrulanamadı."


@pytest.mark.anyio
async def test_require_gateway_secret_success() -> None:
    settings.GATEWAY_SECURITY_ENABLED = True
    # Doğru secret ile hata fırlatmamalı
    await require_gateway_secret(x_gateway_secret=settings.GATEWAY_INTERNAL_SECRET)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_secret",
    [
        None,
        "",
        "wrong-secret",
        "dgl-internal-gateway-secret-token-INVALID",
    ],
)
async def test_require_gateway_secret_missing_or_invalid_raises_403(
    invalid_secret: str | None,
) -> None:
    settings.GATEWAY_SECURITY_ENABLED = True
    with pytest.raises(HTTPException) as exc_info:
        await require_gateway_secret(x_gateway_secret=invalid_secret)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Doğrudan erişim engellendi."
    # Gerçek secret değeri hata mesajında ASLA geçmemeli
    assert settings.GATEWAY_INTERNAL_SECRET not in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_require_gateway_secret_bypassed_when_disabled() -> None:
    settings.GATEWAY_SECURITY_ENABLED = False
    # Güvenlik kapalıyken secret olmasa bile geçmeli
    await require_gateway_secret(x_gateway_secret=None)


def test_api_routes_enforce_gateway_secret_when_enabled() -> None:
    settings.GATEWAY_SECURITY_ENABLED = True
    client = TestClient(app)

    # 1. Secret olmadan istek -> 403 Forbidden
    resp_no_secret = client.post("/rag/search", json={"query": "deneme"})
    assert resp_no_secret.status_code == 403
    assert resp_no_secret.json()["detail"] == "Doğrudan erişim engellendi."
    # Yanıt gövdesinde secret bulunmamalı
    assert settings.GATEWAY_INTERNAL_SECRET not in resp_no_secret.text

    # 2. Yanlış secret ile istek -> 403 Forbidden
    resp_wrong_secret = client.post(
        "/rag/search",
        headers={"X-Gateway-Secret": "tamamen-yanlis-token"},
        json={"query": "deneme"},
    )
    assert resp_wrong_secret.status_code == 403

    # 3. /docs ve /openapi.json muaf olmalı
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize(
    "corr_input,expected_output",
    [
        ("corr-123", "corr-123"),
        ("a\nb", None),
        ("x" * 65, None),
        ("x" * 64, "x" * 64),
        ("<script>", None),
        (None, None),
        ("123e4567-e89b-12d3-a456-426614174000", "123e4567-e89b-12d3-a456-426614174000"),
        ("corr.abc_123-def", "corr.abc_123-def"),
        ("   corr-spaced   ", "corr-spaced"),
    ],
)
async def test_sanitize_correlation_id(corr_input: str | None, expected_output: str | None) -> None:
    valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
    ctx = await get_request_context(x_user_id=valid_uuid, x_correlation_id=corr_input)
    assert ctx.correlation_id == expected_output




@pytest.mark.anyio
async def test_perimeter_denied_audit_records(audit_records: list[dict[str, Any]]) -> None:
    """Çevre güvenliği reddedildiğinde audit kaydı yazıldığını ve secret sızdırılmadığını doğrular."""
    # 1. Eksik kimlik
    with pytest.raises(HTTPException):
        await get_request_context(x_user_id=None)
    assert audit_records[-1]["event"] == "perimeter_denied"
    assert audit_records[-1]["outcome"] == "missing_identity"

    # 2. Geçersiz kimlik
    with pytest.raises(HTTPException):
        await get_request_context(x_user_id="abc")
    assert audit_records[-1]["event"] == "perimeter_denied"
    assert audit_records[-1]["outcome"] == "invalid_identity"

    # 3. Yanlış secret
    settings.GATEWAY_SECURITY_ENABLED = True
    wrong_secret = "attacker-secret-xyz-999"
    with pytest.raises(HTTPException):
        await require_gateway_secret(x_gateway_secret=wrong_secret)
    assert audit_records[-1]["event"] == "perimeter_denied"
    assert audit_records[-1]["outcome"] == "secret_mismatch"

    # Yanlış secret değeri audit kaydında ASLA yer almamalıdır
    assert wrong_secret not in json.dumps(audit_records)
