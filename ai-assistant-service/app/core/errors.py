"""RFC 7807 Problem Details Standart Hata Modeli ve Yakalayıcıları.

AGENTS.md Kuralı: Hata cevapları RFC 7807 ProblemDetails formatında olmalıdır.
application/problem+json içerik türüyle standart hata alanları (type, title, status, detail, instance) döner.
"""

from __future__ import annotations

import http
import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ProblemDetails(BaseModel):
    """RFC 7807 Problem Details standart veri modeli."""

    type: str = Field(default="about:blank", description="Hata tipini tanımlayan URI")
    title: str = Field(description="Kısa ve okunabilir hata başlığı")
    status: int = Field(description="HTTP durum kodu")
    detail: str = Field(description="Bu hata örneğine özgü anlaşılır açıklama")
    instance: str | None = Field(default=None, description="Hatanın gerçekleştiği istek URI yolu")
    errors: list[dict[str, Any]] | None = Field(
        default=None, description="Giriş doğrulama hatalarının ayrıntıları (422 için)"
    )


def register_problem_details_handlers(app: FastAPI) -> None:
    """FastAPI uygulamasına RFC 7807 uyumlu hata yakalayıcılarını kaydeder."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        try:
            status_obj = http.HTTPStatus(exc.status_code)
            title = status_obj.phrase
        except ValueError:
            title = "HTTP Error"

        problem = ProblemDetails(
            type="about:blank",
            title=title,
            status=exc.status_code,
            detail=str(exc.detail),
            instance=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=problem.model_dump(exclude_none=True),
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err.get("loc", []))
            errors.append({
                "field": loc,
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            })

        problem = ProblemDetails(
            type="about:blank",
            title="Unprocessable Entity",
            status=422,
            detail="İstek parametreleri veya gövdesi doğrulanamadı.",
            instance=request.url.path,
            errors=errors,
        )
        return JSONResponse(
            status_code=422,
            content=problem.model_dump(exclude_none=True),
            media_type="application/problem+json",
        )
