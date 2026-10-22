import contextvars
import logging
import uuid
from dataclasses import dataclass, field
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings
from app.core.exceptions import UnauthorizedException, build_problem_detail

logger = logging.getLogger(__name__)

GATEWAY_SECRET_HEADER = "X-Gateway-Secret"
USER_ID_HEADER = "X-User-Id"
USER_EMAIL_HEADER = "X-User-Email"
USER_ROLES_HEADER = "X-User-Roles"
CORRELATION_ID_HEADER = "X-Correlation-Id"
MODEL_PROVIDER_HEADER = "X-Model-Provider"

EXEMPT_PATH_PREFIXES = (
    "/actuator",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/v3/api-docs",
)


@dataclass(frozen=True)
class RequestContext:
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str | None = None
    user_email: str | None = None
    user_roles: str = "ROLE_CUSTOMER"
    model_provider: str | None = None

    @property
    def is_admin(self) -> bool:
        return "ROLE_ADMIN" in (self.user_roles or "")


_request_context_var: contextvars.ContextVar[RequestContext] = contextvars.ContextVar(
    "request_context",
    default=RequestContext(),
)


def get_request_context() -> RequestContext:
    """Returns the current request's security and tracing context."""
    return _request_context_var.get()


def set_request_context(ctx: RequestContext) -> contextvars.Token[RequestContext]:
    """Sets the security and tracing context for the current async execution flow."""
    return _request_context_var.set(ctx)


def require_authenticated_user() -> RequestContext:
    """FastAPI dependency that enforces a verified X-User-Id header from API Gateway."""
    ctx = get_request_context()
    if not ctx.user_id or not ctx.user_id.strip():
        raise UnauthorizedException(
            "Missing verified X-User-Id header. Requests must be authenticated via API Gateway."
        )
    return ctx


class GatewaySecurityMiddleware(BaseHTTPMiddleware):
    """
    Blocks direct microservice access (Gateway Bypass) unless X-Gateway-Secret matches,
    and populates RequestContext (X-User-Id, X-Correlation-Id, X-Model-Provider).
    """

    @staticmethod
    def _is_exempt_path(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        raw_corr_id = request.headers.get(CORRELATION_ID_HEADER)
        correlation_id = raw_corr_id.strip() if raw_corr_id and raw_corr_id.strip() else str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        path = request.url.path

        if settings.GATEWAY_SECRET_ENABLED and not self._is_exempt_path(path):
            received_secret = request.headers.get(GATEWAY_SECRET_HEADER)
            if not received_secret or received_secret != settings.GATEWAY_INTERNAL_SECRET:
                client_host = request.client.host if request.client else "unknown"
                logger.warning(
                    "Blocked direct access attempt to path [%s] from IP [%s]. Missing or invalid %s.",
                    path,
                    client_host,
                    GATEWAY_SECRET_HEADER,
                )
                problem = build_problem_detail(
                    status_code=status.HTTP_403_FORBIDDEN,
                    title="Forbidden",
                    detail="Direct microservice access denied. Requests must be routed through API Gateway.",
                    error_type="https://api.commerce.com/errors/gateway-bypass-forbidden",
                    instance=path,
                    correlation_id=correlation_id,
                )
                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content=problem,
                    media_type="application/problem+json",
                )
                response.headers[CORRELATION_ID_HEADER] = correlation_id
                return response

        ctx = RequestContext(
            correlation_id=correlation_id,
            user_id=request.headers.get(USER_ID_HEADER),
            user_email=request.headers.get(USER_EMAIL_HEADER),
            user_roles=request.headers.get(USER_ROLES_HEADER) or "ROLE_CUSTOMER",
            model_provider=request.headers.get(MODEL_PROVIDER_HEADER),
        )
        token = set_request_context(ctx)
        try:
            response = await call_next(request)
            response.headers[CORRELATION_ID_HEADER] = correlation_id
            return response
        finally:
            _request_context_var.reset(token)
