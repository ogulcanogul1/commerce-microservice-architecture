"""SIGTERM sinyali için graceful drain (zarif boşaltma) işleyicisi."""

import asyncio
from collections.abc import Callable
import logging
import os
import signal
import sys
from typing import Any

from app.discovery.registrar import EurekaRegistrar

logger = logging.getLogger(__name__)

# Güçlü referans saklayıcı (asyncio task'larının çöp toplayıcı tarafından silinmesini engeller)
_drain_tasks: set[asyncio.Task[Any]] = set()


def install_sigterm_drain(
    registrar: EurekaRegistrar,
    drain_sec: int,
) -> Callable[[], None]:
    """SIGTERM sinyali alındığında Eureka'dan çıkıp drain_sec kadar bekleyen sinyal işleyiciyi kurar.

    Neden Lifespan Kapanışında Değil de Sinyal Yakalayıcıda?
    - Uvicorn SIGTERM sinyali aldığında HTTP dinleme soketini ANINDA kapatır.
    - Lifespan shutdown bloğu ise ancak içerideki mevcut istekler bittikten sonra çalışır.
    - Oysa API Gateway, Eureka registry'sini 5-10 saniyelik önbelleklerle okur.
    - Uvicorn soketi kapattığı anda Gateway henüz servisin kapandığını bilmediği için
      eski adrese yeni istekler göndermeye devam eder ve 'Connection Refused' (502/503) hataları oluşur.
    - Bu yüzden SIGTERM anında önce Eureka'dan OUT_OF_SERVICE ve deregister yapılır,
      ardından Gateway'in önbelleğini temizlemesi için 'drain_sec' (20 saniye) kadar beklenir,
      son olarak Uvicorn'un orijinal sinyal işleyicisine devredilir.

    Platform Davranışı:
    - Windows ortamında POSIX sinyal semantiği bulunmadığı için güvenli bir şekilde no-op (etkisiz)
      çalışır ve boş bir geri-alma fonksiyonu döndürür.

    Returns:
        Kurulan sinyal işleyiciyi eski haline döndüren (rollback/restore) çağrılabilir fonksiyon.
    """
    if sys.platform == "win32":
        logger.debug("Windows platformunda SIGTERM drain atlandi (no-op)")
        return lambda: None

    try:
        previous = signal.getsignal(signal.SIGTERM)
    except (ValueError, OSError) as exc:
        logger.warning("SIGTERM sinyali okunamadi (ana thread disinda calisiyor olabilir): %s", exc)
        return lambda: None

    handled = False

    def sigterm_handler(signum: int, frame: Any) -> None:
        nonlocal handled
        if handled:
            return
        handled = True

        logger.info(
            "SIGTERM sinyali yakalandi. Eureka'dan cekilme basliyor (drain bekleme suresi: %d sn)...",
            drain_sec,
        )

        async def _drain_and_forward() -> None:
            try:
                await registrar.drain_and_deregister()
            except Exception:
                logger.exception("Drain sirasinda beklenmeyen hata olustu")

            if drain_sec > 0:
                logger.info("Gateway onbelleginin bosalmasi icin %d sn bekleniyor...", drain_sec)
                await asyncio.sleep(drain_sec)

            logger.info("Drain suresi tamamlandi, uvicorn orijinal sinyal isleyicisine devrediliyor")
            if callable(previous):
                previous(signum, frame)
            else:
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                os.kill(os.getpid(), signal.SIGTERM)

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_drain_and_forward())
            _drain_tasks.add(task)
            task.add_done_callback(_drain_tasks.discard)
        except RuntimeError:
            # Calisan bir event loop yoksa dogrudan senkron cagir
            logger.warning("Calisan event loop bulunamadi, sinyal dogrudan devrediliyor")
            if callable(previous):
                previous(signum, frame)

    try:
        signal.signal(signal.SIGTERM, sigterm_handler)
    except (ValueError, OSError) as exc:
        logger.warning("SIGTERM isleyici kaydedilemedi (ana thread disinda calisiyor olabilir): %s", exc)
        return lambda: None

    def restore() -> None:
        try:
            signal.signal(signal.SIGTERM, previous)
        except (ValueError, OSError):
            pass

    return restore
