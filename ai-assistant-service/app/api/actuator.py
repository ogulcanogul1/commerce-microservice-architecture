"""Spring Boot Actuator ile Uyumlu Canlı Yenileme (Refresh) Uç Noktası.

Bu modül, platformdaki Spring Boot Actuator standartlarıyla (POST /actuator/refresh)
tam uyumlu olarak çalışır.

Kullanım:
    POST /actuator/refresh
    Yanıt:
        200 OK + ["ai.agent.max-steps", "ai.rag.top-k"]  (Değişen anahtarların listesi)
        200 OK + []  (Değişiklik yoksa boş liste)
        503 Service Unavailable  (Config Server entegrasyonu aktif değilse)
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.runtimeconfig.paths import flatten_paths

router = APIRouter(prefix="/actuator", tags=["Actuator"])
logger = logging.getLogger(__name__)

# Eşzamanlı refresh çağrılarında yarış durumunu önlemek için kilit
_refresh_lock = asyncio.Lock()


@router.post("/refresh")
async def refresh_runtime_config(request: Request) -> list[str]:
    """Config Server'dan güncel ayarları çeker ve container'ı kapatmadan canlıda günceller.

    Spring Boot Actuator sözleşmesine tam uyumlu olarak:
    - Başarılı ve ayarlar değiştiyse: 200 OK + değişen anahtar listesi (örn: ["ai.agent.max-steps"])
    - Başarılı ama ayarlar aynıysa: 200 OK + []
    - Config Server erişilemez veya hatalıysa: 503 Service Unavailable (hatayı gizlemez)
    """
    holder = getattr(request.app.state, "runtime_config", None)
    client = getattr(request.app.state, "config_server_client", None)

    if holder is None or client is None:
        raise HTTPException(
            status_code=503,
            detail="Config Server entegrasyonu bu instance üzerinde aktif değil.",
        )

    async with _refresh_lock:
        old_dump = holder.current.model_dump()
        old_flat = flatten_paths(old_dump)
        old_version = holder.version

        success = await holder.refresh(client, settings.SERVICE_NAME, settings.CONFIG_PROFILE)
        if not success:
            last_err = holder.status.last_error or "unknown"
            logger.error("POST /actuator/refresh başarısız: %s", last_err)
            raise HTTPException(
                status_code=503,
                detail=f"Config Server yenileme başarısız: {last_err}",
            )

        if holder.version == old_version:
            return []

        # Değişen anahtarları tespit et ve Spring tarzı nokta-kebab formatına çevir
        new_flat = flatten_paths(holder.current.model_dump())
        changed_keys = [
            f"ai.{path.replace('_', '-')}"
            for path in new_flat
            if path in old_flat and old_flat[path] != new_flat[path]
        ]

        return changed_keys
