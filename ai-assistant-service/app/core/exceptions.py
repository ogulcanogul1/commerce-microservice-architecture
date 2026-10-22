from datetime import datetime, timezone
from typing import Any
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class NonRetryableError(Exception):
    """Marker base class for permanent business rule or client validation errors (4xx)."""


class RetryableError(Exception):
    """Marker base class for transient infrastructure or downstream network errors (5xx)."""


class BusinessRuleException(NonRetryableError):
    """Domain/business rule violation that must fail fast and never be retried."""

    def __init__(
        self,
        detail: str,
        title: str = "Business Rule Violation",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_type: str = "https://api.commerce.com/errors/business-rule-violation",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.title = title
        self.status_code = status_code
        self.error_type = error_type


class AccessDeniedException(BusinessRuleException):
    """Raised when a user attempts to access or modify another customer's resource (IDOR)."""

    def __init__(
        self,
        detail: str = "Access denied: you do not have permission to access this resource",
    ) -> None:
        super().__init__(
            detail=detail,
            title="Forbidden",
            status_code=status.HTTP_403_FORBIDDEN,
            error_type="https://api.commerce.com/errors/access-denied",
        )


class UnauthorizedException(BusinessRuleException):
    """Raised when user identity headers or authentication tokens are missing."""

    def __init__(
        self,
        detail: str = "Authentication required: missing verified user context",
    ) -> None:
        super().__init__(
            detail=detail,
            title="Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_type="https://api.commerce.com/errors/unauthorized",
        )


class ResourceNotFoundException(BusinessRuleException):
    """Raised when a requested entity (order, product, shipment) does not exist."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            detail=detail,
            title="Resource Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            error_type="https://api.commerce.com/errors/not-found",
        )


class TransientException(RetryableError):
    """Raised when a downstream microservice, LLM provider, Redis, or Kafka experiences a temporary failure."""

    def __init__(
        self,
        detail: str,
        title: str = "Service Temporarily Unavailable",
        status_code: int = status.HTTP_503_SERVICE_UNAVAILABLE,
        error_type: str = "https://api.commerce.com/errors/transient-failure",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.title = title
        self.status_code = status_code
        self.error_type = error_type


def build_problem_detail(
    *,
    status_code: int,
    title: str,
    detail: str,
    error_type: str,
    instance: str,
    correlation_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    problem: dict[str, Any] = {
        "type": error_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if correlation_id:
        problem["correlationId"] = correlation_id
    if extra:
        problem.update(extra)
    return problem


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessRuleException)
    async def handle_business_rule_exception(
        request: Request, exc: BusinessRuleException
    ) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        payload = build_problem_detail(
            status_code=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            error_type=exc.error_type,
            instance=str(request.url.path),
            correlation_id=correlation_id,
            extra={"retryable": False},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=payload,
            media_type="application/problem+json",
        )

    @app.exception_handler(TransientException)
    async def handle_transient_exception(
        request: Request, exc: TransientException
    ) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        payload = build_problem_detail(
            status_code=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            error_type=exc.error_type,
            instance=str(request.url.path),
            correlation_id=correlation_id,
            extra={"retryable": True},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=payload,
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        payload = build_problem_detail(
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Validation Error",
            detail="Request validation failed",
            error_type="https://api.commerce.com/errors/validation-error",
            instance=str(request.url.path),
            correlation_id=correlation_id,
            extra={"errors": exc.errors(), "retryable": False},
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=payload,
            media_type="application/problem+json",
        )
