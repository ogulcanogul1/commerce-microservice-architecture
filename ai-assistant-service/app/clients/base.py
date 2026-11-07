"""Base HTTP client for downstream microservices communication.

Enforces unified headers (X-Gateway-Secret, X-User-Id, X-Correlation-Id),
blocks privileged headers (X-User-Roles), translates HTTP/network errors into
safe domain exceptions, and implements idempotent retries for GET requests.
"""

from typing import Any
import httpx

from app.core.config import settings


class DownstreamError(Exception):
    """Base exception for all downstream microservice communication errors."""


class DownstreamNotFound(DownstreamError):
    """Raised when a downstream entity is not found (HTTP 404)."""


class DownstreamForbidden(DownstreamError):
    """Raised when caller lacks permission to access downstream entity (HTTP 403)."""


class DownstreamBadRequest(DownstreamError):
    """Raised on invalid request parameters or business validation errors (HTTP 400)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class DownstreamUnavailable(DownstreamError):
    """Raised when downstream service is unreachable, timed out, or returned 5xx."""


class DownstreamClient:
    """Wrapper around httpx.AsyncClient with security headers and safe error handling."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_sec: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        timeout = timeout_sec if timeout_sec is not None else settings.DOWNSTREAM_TIMEOUT_SEC
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client session."""
        await self._client.aclose()

    def _build_headers(
        self,
        *,
        user_id: str,
        correlation_id: str | None = None,
    ) -> dict[str, str]:
        """Construct secure headers. Strictly omits X-User-Roles to prevent privilege escalation."""
        headers: dict[str, str] = {
            "Accept": "application/json",
            "X-Gateway-Secret": settings.GATEWAY_INTERNAL_SECRET,
            "X-User-Id": user_id,
        }
        if correlation_id:
            headers["X-Correlation-Id"] = correlation_id
        return headers

    def _handle_response_status(self, response: httpx.Response) -> None:
        """Map HTTP error status codes to safe domain exceptions without leaking secret/raw URL."""
        if response.status_code == 404:
            raise DownstreamNotFound("İstenen kayıt bulunamadı.")
        if response.status_code == 403:
            raise DownstreamForbidden("Bu kayda erişim yetkisi yok.")
        if response.status_code == 400:
            detail = "Geçersiz istek parametreleri."
            try:
                body = response.json()
                if isinstance(body, dict):
                    detail = body.get("detail") or body.get("message") or detail
            except Exception:
                pass
            raise DownstreamBadRequest(detail=str(detail))
        if response.status_code >= 500:
            raise DownstreamUnavailable("Servis geçici olarak kullanılamıyor.")

    async def get_json(
        self,
        path: str,
        *,
        user_id: str,
        correlation_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Execute an idempotent GET request with 1 retry on network/transport connection failure."""
        headers = self._build_headers(user_id=user_id, correlation_id=correlation_id)
        max_attempts = 2  # 1 initial + 1 retry on connection error

        for attempt in range(max_attempts):
            try:
                response = await self._client.get(path, headers=headers, params=params)
                self._handle_response_status(response)
                response.raise_for_status()
                return response.json()
            except (DownstreamNotFound, DownstreamForbidden, DownstreamBadRequest, DownstreamUnavailable):
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
                if attempt == max_attempts - 1:
                    raise DownstreamUnavailable("Servise ulaşılamadı veya zaman aşımı oluştu.") from exc
            except Exception as exc:
                raise DownstreamUnavailable("Servis isteği sırasında beklenmeyen bir hata oluştu.") from exc

        raise DownstreamUnavailable("Servis geçici olarak kullanılamıyor.")

    async def post_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        user_id: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Execute a non-idempotent POST request. NEVER retried automatically on failure."""
        headers = self._build_headers(user_id=user_id, correlation_id=correlation_id)
        try:
            response = await self._client.post(path, json=body, headers=headers)
            self._handle_response_status(response)
            response.raise_for_status()
            return response.json()
        except (DownstreamNotFound, DownstreamForbidden, DownstreamBadRequest, DownstreamUnavailable):
            raise
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
            raise DownstreamUnavailable("Servise ulaşılamadı veya zaman aşımı oluştu.") from exc
        except Exception as exc:
            raise DownstreamUnavailable("Servis isteği sırasında beklenmeyen bir hata oluştu.") from exc
