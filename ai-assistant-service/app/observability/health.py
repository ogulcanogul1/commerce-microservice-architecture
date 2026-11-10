"""Liveness ve Readiness sağlık denetimi mantık modülü.

MİMARİ PRENSİP:
Bu modüldeki kontroller hızlı, içsel ve hafif olmalıdır.
1. Liveness: Event loop'un yanıt verip vermediğini doğrular. Donma/deadlock yoksa her zaman canlıdır.
2. Readiness: Pod'un kullanıcı trafiği alabilecek durumda olup olmadığını kontrol eder.

BİLEREK KAPSAM DIŞI BIRAKILANLAR:
- Harici LLM Sağlayıcısı (Gemini, OpenAI): Dış sağlayıcı kesintisi pod'ları NotReady yaparak trafiği
  kesmemelidir. LLM arızaları pod öldürülerek değil, uygulama içindeki fallback mekanizmasıyla yönetilir.
- Downstream Servisler (order-service, shipping-service): Downstream kesintileri circuit breaker ile yönetilir.
- Qdrant ve Kafka: KafkaTicketPublisher producer'ı ilk publish'te tembel (lazy) başlattığı için
  açılışta yapılacak bir bağlantı kontrolü yanlış alarm (false-positive) üretir. Kafka kesintisi publish anında yönetilir.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.discovery.drain import is_draining


@dataclass(frozen=True)
class ReadinessResult:
    """Readiness kontrolü sonucu ve alt bileşenlerin sağlık durumları."""
    ready: bool
    components: dict[str, str]  # {"startup": "UP", "drain": "UP", "redis": "UP"|"DOWN"|"DISABLED"}


async def check_readiness(
    app_state: Any,
    redis_ping: Any = None,
    *,
    timeout_sec: float = 1.0,
) -> ReadinessResult:
    """FastAPI uygulama durumunu (app.state) ve Redis durumunu inceleyerek hazır olup olmadığını belirler.
    
    Kontroller:
    - startup: lifespan açılış adımlarını tamamlayıp `app.state.ready = True` yaptı mı?
    - drain: SIGTERM drain sinyali alındı mı? (`app.state.draining` veya `is_draining()`)
    - redis: REDIS_ENABLED=True ise Redis ping'i başarılı mı? (Kapalıysa DISABLED kabul edilir)
    """
    components: dict[str, str] = {}
    is_ready = True

    # 1. Başlangıç (Startup) kontrolü
    if getattr(app_state, "ready", False):
        components["startup"] = "UP"
    else:
        components["startup"] = "DOWN"
        is_ready = False

    # 2. Boşaltma (Drain) kontrolü: SIGTERM alındıysa yeni trafik kabul edilmez
    if getattr(app_state, "draining", False) or is_draining():
        components["drain"] = "DOWN"
        is_ready = False
    else:
        components["drain"] = "UP"

    # 3. Redis kontrolü (Yalnızca REDIS_ENABLED aktifse)
    if not settings.REDIS_ENABLED:
        components["redis"] = "DISABLED"
    else:
        ping_fn = redis_ping
        if ping_fn is None:
            redis_client = getattr(app_state, "redis_client", None)
            if redis_client is not None and hasattr(redis_client, "ping"):
                ping_fn = redis_client.ping

        if ping_fn is not None:
            try:
                pong = ping_fn()
                if asyncio.iscoroutine(pong):
                    pong = await asyncio.wait_for(pong, timeout=timeout_sec)
                components["redis"] = "UP" if pong else "DOWN"
            except Exception:
                components["redis"] = "DOWN"
        else:
            components["redis"] = "DOWN"

        if components["redis"] == "DOWN":
            is_ready = False

    return ReadinessResult(ready=is_ready, components=components)
