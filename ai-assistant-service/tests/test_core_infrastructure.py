from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.exceptions import (
    AccessDeniedException,
    BusinessRuleException,
    NonRetryableError,
    RetryableError,
    TransientException,
)
from app.core.security import (
    CORRELATION_ID_HEADER,
    GATEWAY_SECRET_HEADER,
    MODEL_PROVIDER_HEADER,
    USER_EMAIL_HEADER,
    USER_ID_HEADER,
    USER_ROLES_HEADER,
    RequestContext,
    require_authenticated_user,
)
from app.main import create_app


def _build_test_app():
    app = create_app()

    @app.get("/api/v1/test-context")
    async def get_test_context(
        ctx: RequestContext = Depends(require_authenticated_user),
    ) -> dict:
        return {
            "userId": ctx.user_id,
            "email": ctx.user_email,
            "roles": ctx.user_roles,
            "isAdmin": ctx.is_admin,
            "correlationId": ctx.correlation_id,
            "modelProvider": ctx.model_provider,
        }

    @app.get("/api/v1/test-business-error")
    async def trigger_business_error() -> None:
        raise AccessDeniedException("Cannot view another customer's order")

    @app.get("/api/v1/test-transient-error")
    async def trigger_transient_error() -> None:
        raise TransientException("Downstream order-service timed out")

    return app


def test_actuator_health_and_info_are_exempt_from_gateway_secret():
    client = TestClient(_build_test_app())

    health_res = client.get("/actuator/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "UP"
    assert CORRELATION_ID_HEADER in health_res.headers

    info_res = client.get("/actuator/info")
    assert info_res.status_code == 200
    assert info_res.json()["app"]["name"] == "ai-assistant-service"


def test_gateway_bypass_is_blocked_with_rfc7807_problem_detail():
    client = TestClient(_build_test_app())

    res = client.get("/api/v1/test-context")
    assert res.status_code == 403
    assert "application/problem+json" in res.headers["content-type"]
    body = res.json()
    assert body["title"] == "Forbidden"
    assert body["status"] == 403
    assert body["type"] == "https://api.commerce.com/errors/gateway-bypass-forbidden"


def test_missing_user_id_header_returns_401_problem_detail():
    client = TestClient(_build_test_app())

    res = client.get(
        "/api/v1/test-context",
        headers={GATEWAY_SECRET_HEADER: settings.GATEWAY_INTERNAL_SECRET},
    )
    assert res.status_code == 401
    body = res.json()
    assert body["title"] == "Unauthorized"
    assert body["retryable"] is False


def test_valid_gateway_and_user_headers_populate_request_context():
    client = TestClient(_build_test_app())
    corr_id = "11111111-2222-3333-4444-555555555555"

    res = client.get(
        "/api/v1/test-context",
        headers={
            GATEWAY_SECRET_HEADER: settings.GATEWAY_INTERNAL_SECRET,
            USER_ID_HEADER: "99999999-8888-7777-6666-555555555555",
            USER_EMAIL_HEADER: "ayse@example.com",
            USER_ROLES_HEADER: "ROLE_CUSTOMER,ROLE_ADMIN",
            CORRELATION_ID_HEADER: corr_id,
            MODEL_PROVIDER_HEADER: "claude",
        },
    )
    assert res.status_code == 200
    assert res.headers[CORRELATION_ID_HEADER] == corr_id
    data = res.json()
    assert data["userId"] == "99999999-8888-7777-6666-555555555555"
    assert data["email"] == "ayse@example.com"
    assert data["isAdmin"] is True
    assert data["correlationId"] == corr_id
    assert data["modelProvider"] == "claude"


def test_exception_classification_and_rfc7807_handlers():
    assert issubclass(BusinessRuleException, NonRetryableError)
    assert issubclass(TransientException, RetryableError)

    client = TestClient(_build_test_app())
    headers = {GATEWAY_SECRET_HEADER: settings.GATEWAY_INTERNAL_SECRET}

    res_biz = client.get("/api/v1/test-business-error", headers=headers)
    assert res_biz.status_code == 403
    assert res_biz.json()["retryable"] is False

    res_trans = client.get("/api/v1/test-transient-error", headers=headers)
    assert res_trans.status_code == 503
    assert res_trans.json()["retryable"] is True
