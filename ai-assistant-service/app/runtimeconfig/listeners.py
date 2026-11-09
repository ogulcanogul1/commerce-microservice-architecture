"""Runtime Konfigürasyon Dinleyicileri (Listeners).

Bu modül, konfigürasyon değiştiğinde (veya ilk yüklendiğinde) anlık olarak
uygulanması gereken sistem yan etkilerini (side-effects) yönetir.
"""

import logging

from app.runtimeconfig.models import RuntimeSettings

logger = logging.getLogger(__name__)


def apply_log_level(old: RuntimeSettings | None, new: RuntimeSettings) -> None:
    """Config Server'daki 'ai.logging.level' ayarını canlıda 'app' logger'ına uygular.

    Güvenlik ve İzolasyon Kuralı:
    Yalnızca bizim uygulama kodlarımızın bulunduğu "app" logger'ının seviyesi değiştirilir.
    Kök (root) logger'a ve Uvicorn'a kesinlikle dokunulmaz; aksi takdirde HTTP erişim logları
    veya kütüphane logları kontrolsüzce açılarak log kirliliği ve performans kaybı oluşur.

    Args:
        old: Önceki konfigürasyon (başlangıçta None olabilir).
        new: Yeni konfigürasyon.
    """
    old_level = old.logging.level if old else None
    new_level = new.logging.level

    if old is None or old_level != new_level:
        target_logger = logging.getLogger("app")
        if new_level is None:
            # None ise varsayılan hiyerarşiye (NOTSET) bırakılır
            target_logger.setLevel(logging.NOTSET)
            logger.info("Uygulama ('app') log seviyesi varsayılana çekildi (NOTSET)")
        else:
            log_level_int = getattr(logging, new_level, logging.INFO)
            target_logger.setLevel(log_level_int)
            logger.info("Uygulama ('app') log seviyesi dinamik olarak değiştirildi: %s", new_level)
