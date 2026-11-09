"""FastAPI İstek Başına (Per-Request) Runtime Konfigürasyon Bağımlılığı.

Bu modül, her gelen HTTP isteği için o anki dondurulmuş (frozen) RuntimeSettings
snapshot'ını sağlar.

Dağıtık Sistem İlkesi (Per-Request Snapshot):
İstek başında alınan snapshot, tur boyunca tüm LLM ve araç çağrılarına parametre
olarak geçirilir. İstek işlenirken arka planda konfigürasyon güncellense dahi,
çalışan istek eski kurallarla güvenle sonlanır; yarım/karışık ayar kullanımı engellenir.
"""

from fastapi import Request

from app.core.config import settings
from app.runtimeconfig.models import RuntimeSettings


def get_runtime_settings(request: Request) -> RuntimeSettings:
    """İstek başına TEK ve değişmez (immutable) konfigürasyon snapshot'ı döndürür."""
    holder = getattr(request.app.state, "runtime_config", None)
    if holder is None:
        return RuntimeSettings.from_startup(settings)
    return holder.current
