"""Actuator gözlemlenebilirlik uç noktaları (Prometheus, Liveness, Readiness).

Bu yönlendirici (Router) Prometheus ve orkestratörler (Kubernetes, Docker Swarm) için
gerekli gözetim endpoint'lerini sunar:
- GET /actuator/prometheus: Prometheus formatında tüm metrik çıktısı.
- GET /actuator/health/liveness: Sürecin kilitlenip kilitlenmediğini teyit eden canlılık probu.
- GET /actuator/health/readiness: Trafik almaya hazır olunup olunmadığını bildiren hazırlık probu.

GÜVENLİK NOTU:
Bu router `require_gateway_secret` BAĞIMLILIĞI OLMADAN açılır.
Prometheus v2.51 scrape sırasında özel header iletemez; ayrıca mikroservis portu (8089)
dış dünyaya kapalıdır (yalnızca dahili ağdadır) ve Gateway bu yolları dışarıya yönlendirmez.
Mevcut /actuator/refresh ise ayrı router'da gizli anahtarla korunmaya devam eder.
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.observability.health import check_readiness

observability_router = APIRouter(prefix="/actuator", tags=["Observability"])


@observability_router.get("/prometheus", summary="Prometheus Metrik Çıktısı")
async def prometheus_metrics() -> Response:
    """Prometheus sunucusunun düzenli aralıklarla scrape ettiği metrik çıktısı."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@observability_router.get("/health/liveness", summary="Liveness Canlılık Probu")
async def liveness_probe() -> dict[str, str]:
    """Süreç event loop'unun hayatta ve cevap verebilir olduğunu doğrular."""
    return {"status": "UP"}


@observability_router.get("/health/readiness", summary="Readiness Hazırlık Probu")
async def readiness_probe(request: Request) -> JSONResponse:
    """Pod'un kullanıcı trafiği alabilecek durumda olup olmadığını kontrol eder.
    
    Spring Boot Actuator sözleşmesiyle birebir uyumludur:
    - Hazırsa: HTTP 200 {"status": "UP", "components": {...}}
    - Hazır değilse veya drain modundaysa: HTTP 503 {"status": "OUT_OF_SERVICE", "components": {...}}
    """
    result = await check_readiness(request.app.state)
    status_code = 200 if result.ready else 503
    payload = {
        "status": "UP" if result.ready else "OUT_OF_SERVICE",
        "components": result.components,
    }
    return JSONResponse(status_code=status_code, content=payload)
