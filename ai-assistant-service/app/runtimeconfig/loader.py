"""Config Server Başlangıç Yükleyicisi (Initial Loader).

Bu modül, mikroservis ayağa kalkarken (FastAPI lifespan) Spring Cloud Config Server'a
bağlanarak ilk konfigürasyonu çeker.

Mimari Kurallar:
1. Üstel Geri Çekilme (Exponential Backoff): Config Server henüz ayağa kalkıyorsa
   1s, 2s aralıklarla en fazla 'attempts' (varsayılan: 3) kez dener.
2. Akıllı Hata Ayrımı:
   - Ağ veya geçici sunucu hatalarında (fetch) tekrar dener.
   - Ancak format veya doğrulama hatasıysa (Config Server'daki dosya bozuksa),
     tekrar denemek anlamsızdır (aynı dosya gelecektir). Döngü derhal kırılır ve
     fail-soft olarak yerel baseline konfigürasyonuyla devam edilir.
"""

import asyncio
import logging

from app.runtimeconfig.client import ConfigServerClient
from app.runtimeconfig.holder import RuntimeConfigHolder

logger = logging.getLogger(__name__)


async def initial_load(
    holder: RuntimeConfigHolder,
    client: ConfigServerClient,
    app_name: str,
    profile: str,
    attempts: int = 3,
    backoff_sec: float = 1.0,
) -> bool:
    """Açılışta Config Server'dan konfigürasyonu çekmeyi dener.

    Args:
        holder: Konfigürasyon taşıyıcı nesnesi.
        client: Config Server REST istemcisi.
        app_name: Uygulama adı (örn: 'ai-assistant-service').
        profile: Konfigürasyon profili (örn: 'dev', 'qa', 'prod').
        attempts: Maksimum deneme sayısı (varsayılan: 3).
        backoff_sec: Denemeler arası taban bekleme süresi (varsayılan: 1.0s).

    Returns:
        Konfigürasyon başarıyla alındıysa True; alınamadıysa False.
    """
    for i in range(attempts):
        success = await holder.refresh(client, app_name, profile)
        if success:
            logger.info("Config Server başlangıç konfigürasyonu başarıyla yüklendi (deneme %d/%d).", i + 1, attempts)
            return True

        # Eğer hata geçersiz şema veya format ise tekrar denemek anlamsızdır
        if holder.status.last_error in ("format", "validation"):
            logger.warning(
                "Config Server dosyası geçersiz şema/format içeriyor; yerel varsayılanlarla devam ediliyor."
            )
            return False

        # Son denemeden sonra bekleme yapılmaz
        if i < attempts - 1:
            wait_time = backoff_sec * (2**i)
            logger.warning(
                "Config Server'a bağlanılamadı (deneme %d/%d). %.1f saniye sonra tekrar denenecek...",
                i + 1,
                attempts,
                wait_time,
            )
            await asyncio.sleep(wait_time)

    return False
