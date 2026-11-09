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

import logging
from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.runtimeconfig.paths import flatten_paths

router = APIRouter(prefix="/actuator", tags=["Actuator"])
logger = logging.getLogger(__name__)


@router.post("/refresh")
async def refresh_runtime_config(request: Request) -> list[str]:
    """Config Server'dan güncel ayarları çeker ve container'ı kapatmadan canlıda günceller.

    Spring Boot Actuator sözleşmesine tam uyumlu olarak değişen ayar anahtarlarının
    listesini döner (örn: ["ai.agent.max-steps"]).
    """
    holder = getattr(request.app.state, "runtime_config", None)
    client = getattr(request.app.state, "config_server_client", None)

    if holder is None or client is None:
        raise HTTPException(
            status_code=503,
            detail="Config Server entegrasyonu bu instance üzerinde aktif değil.",
        )

    # Değişiklik farkını (diff) hesaplamak için mevcut ayarların düz haritasını alıyoruz
    old_dump = holder.current.model_dump()
    old_flat = flatten_paths(old_dump)

    # Config Server'dan yeni ayarları çek ve atomik olarak uygula
    changed = await holder.refresh(client, settings.SERVICE_NAME, settings.CONFIG_PROFILE)

    if not changed:
        return []

    # Değişen anahtarları tespit et ve Spring tarzı nokta-kebab formatına çevir
    new_flat = flatten_paths(holder.current.model_dump())
    changed_keys = [
        f"ai.{path.replace('_', '-')}"
        for path in new_flat
        if path in old_flat and old_flat[path] != new_flat[path]
    ]

    return changed_keys
