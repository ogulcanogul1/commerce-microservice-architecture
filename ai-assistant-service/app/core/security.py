"""Security dependencies and request context for ai-assistant-service.

Enforces perimeter security via API Gateway secret validation and extracts
authenticated caller identity (X-User-Id) into an immutable RequestContext.
"""

from dataclasses import dataclass
import hmac
import re
import uuid

from fastapi import Header, HTTPException, status

from app.core.audit import write_audit
from app.core.config import settings

# Gateway UUID üretir; harf, rakam, nokta, alt çizgi ve tire dışındakini kabul etme
_CORRELATION_ID_PATTERN = re.compile(r"[A-Za-z0-9._\-]{1,64}")


def _sanitize_correlation_id(value: str | None) -> str | None:
    """Geçerli değilse None döner; ham değer loglanmaz."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if _CORRELATION_ID_PATTERN.fullmatch(stripped) else None


@dataclass(frozen=True)
class RequestContext:
    """Immutable request context carrying validated user identity and correlation tracking."""

    user_id: str  # Lowercase, hyphenated standard UUID (e.g. '123e4567-e89b-12d3-a456-426614174000')
    correlation_id: str | None


async def get_request_context(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-Id"),
) -> RequestContext:
    """Validate and extract caller identity from the X-User-Id gateway header.

    Raises:
        HTTPException(401): If X-User-Id header is missing, empty, or not a valid UUID.

    Returns:
        RequestContext: Normalized user_id and optional correlation_id.
    """
    if not x_user_id or not x_user_id.strip():
        write_audit("perimeter_denied", user_id=None, correlation_id=None, outcome="missing_identity")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kimlik doğrulanamadı.",
        )

    try:
        parsed_uuid = uuid.UUID(x_user_id.strip())
    except (ValueError, AttributeError):
        write_audit("perimeter_denied", user_id=None, correlation_id=None, outcome="invalid_identity")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kimlik doğrulanamadı.",
        )

    normalized_user_id = str(parsed_uuid).lower()
    return RequestContext(
        user_id=normalized_user_id,
        correlation_id=_sanitize_correlation_id(x_correlation_id),
    )


async def require_gateway_secret(
    x_gateway_secret: str | None = Header(None, alias="X-Gateway-Secret"),
) -> None:
    """Enforce API Gateway secret header to prevent direct unauthenticated perimeter bypass.

    Uses constant-time comparison (hmac.compare_digest) to prevent timing attacks.
    Never reflects the secret token in error details or logs.

    Raises:
        HTTPException(403): If the secret header is missing or does not match.
    """
    if not settings.GATEWAY_SECURITY_ENABLED:
        return

    expected_secret = settings.GATEWAY_INTERNAL_SECRET
    if not x_gateway_secret or not hmac.compare_digest(x_gateway_secret, expected_secret):
        write_audit("perimeter_denied", user_id=None, correlation_id=None, outcome="secret_mismatch")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doğrudan erişim engellendi.",
        )
