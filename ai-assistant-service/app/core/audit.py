"""Ayrık Denetim İzi ve Güvenlik Audit Günlüğü (Security Audit Logging).

Bu modül, mikroservisin normal uygulama loglarından (application logs) TAMAMEN AYRI bir
denetim ve güvenlik izi (audit trail) oluşturur.

MİMARİ VE GÜVENLİK İLKELERİ:
1. PII (Kişisel Veri) Hijyeni:
   Audit kayıtlarına asla müşteri adı, açık adres veya sipariş detayı yazılmaz. Fonksiyonlara
   gönderilen argümanlar yalnızca isim listesi (`arg_names`) ve 16 karakterlik SHA-256 özeti
   (`args_hash`) olarak kaydedilir.
2. Kimlik Takma Adı (Pseudonym):
   Kullanıcı kimliği yalnızca standart UUID (`user_id`) olarak tutulur; e-posta/telefon girmez.
3. Ayrık Akış (No Propagation):
   `audit` logger'ının `propagate` değeri `False` yapılır; böylece audit kayıtları root logger'a
   ve genel uygulama loglarına sızmaz, stdout'a salt JSON satırları halinde basılır. SIEM
   (Loki, Elasticsearch) bu akışı ayrı indeksler.
4. Fail-Safe Yazım:
   Audit kaydı atılırken oluşabilecek herhangi bir istisna (disk/json hatası vb.) ASLA yukarıya
   fırlatılmaz ve ana iş akışını (sipariş sorgulama/iptal) durdurmaz.
5. Enumeration / IDOR Tespiti:
   Kullanıcıların başkalarına ait siparişleri veya kaynakları art arda denemesini (tarama saldırısı)
   yakalayan süreç içi bir sayaç (`DenyTracker`) içerir.
"""

import asyncio
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import logging
import sys
import threading
import time
from typing import Any
import uuid

# Denetim kayıtlarının toplandığı özel ayrık logger adı
AUDIT_LOGGER_NAME = "audit"
logger = logging.getLogger(__name__)

# ==============================================================================
# 1. STANDART AUDIT SONUÇ KODLARI (OUTCOMES)
# ==============================================================================
# Tüm araç ve güvenlik kontrolleri sonuçlarını bu standart kodlarla etiketler:
OUTCOME_OK = "ok"                                      # İşlem başarılı
OUTCOME_DENIED = "denied"                              # Downstream servis 403 Forbidden döndü
OUTCOME_OWNERSHIP_MISMATCH = "ownership_mismatch"      # Python katmanındaki sahiplik kontrolü yetkisiz erişimi yakaladı
OUTCOME_NOT_FOUND = "not_found"                        # İstenen kaynak bulunamadı (404)
OUTCOME_INVALID_ARGS = "invalid_args"                  # Şema/tip doğrulama hatası
OUTCOME_BAD_REQUEST = "bad_request"                    # Geçersiz istek parametresi
OUTCOME_TIMEOUT = "timeout"                            # İşlem zaman aşımına uğradı
OUTCOME_UNAVAILABLE = "unavailable"                    # Hedef mikroservis kapalı/erişilemiyor
OUTCOME_ERROR = "error"                                # Beklenmeyen genel sistem hatası

# Saldırganın kaynak taraması (enumeration) yaptığına işaret eden şüpheli sonuçlar kümesi
DENY_OUTCOMES = frozenset({OUTCOME_DENIED, OUTCOME_OWNERSHIP_MISMATCH, OUTCOME_NOT_FOUND})


# ==============================================================================
# 2. AUDIT LOGGER KURULUMU VE İZOLASYONU
# ==============================================================================

def get_audit_logger() -> logging.Logger:
    """Ayrık, ana loglara yayılmayan (propagate=False) ve stdout'a düz JSON basan logger'ı döner."""
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    if not audit_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)
    # Ana root logger'a log aktarımını engelle (Log ayrıştırması ve caplog izolasyonu için kritik)
    audit_logger.propagate = False
    return audit_logger


# ==============================================================================
# 3. ARGÜMAN HASHLEME VE GÜVENLİ AUDIT YAZIMI
# ==============================================================================

def hash_args(args: Any) -> str:
    """Argüman sözlüğünün tek yönlü kısa (16 karakter) SHA-256 özetini üretir.

    Neden Yapılır?
    Sipariş numaraları veya parametreler audit loguna açıkça yazılırsa kişisel veriler sızabilir.
    Bunun yerine deterministik bir hash (`args_hash`) tutulur. Gerektiğinde denetçi, elindeki şüpheli
    parametre setinin aynı hash'i verip vermediğini doğrulayabilir ama hash'ten geriye değer okunamaz.
    """
    try:
        canonical = json.dumps(args if args is not None else {}, sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        canonical = "<unserializable>"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def write_audit(
    event: str,
    *,
    user_id: str | None,
    correlation_id: str | None,
    outcome: str,
    **fields: Any,
) -> None:
    """Tek satırlık standart JSON audit kaydı üretir ve stdout'a basar.

    Alanlar:
    - event: Olayın adı (örn. 'tool_call', 'perimeter_denied', 'action_confirm', 'enumeration_suspected')
    - timestamp: UTC ISO-8601 milisaniye hassasiyetli zaman damgası
    - user_id: Kullanıcının UUID'si
    - correlation_id: İstek izleme kimliği
    - outcome: İşlemin sonucu (ok, denied, timeout, error vb.)
    - fields: Ek güvenli meta veriler (tool adı, argüman isimleri, süre vb.)
    """
    try:
        record: dict[str, Any] = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "user_id": user_id,
            "correlation_id": correlation_id,
            "outcome": outcome,
            **fields,
        }
        get_audit_logger().info(json.dumps(record, ensure_ascii=False, default=str))
    except Exception:
        # Fail-Safe Kuralı: Audit yazımındaki bir hata asla ana iş mantığını (FastAPI handler) bozmamalıdır
        logging.getLogger(__name__).warning("Audit kaydı yazılamadı (event=%s)", event)


# ==============================================================================
# 4. ENUMERATION / TARAMA SALDIRISI TAKİPÇİSİ (DenyTracker)
# ==============================================================================

class InMemoryDenyTracker:
    """Kullanıcı bazında kayan zaman penceresinde (sliding window) reddedilen erişimleri sayar.

    Amaç:
    Bir saldırgan art arda başkalarına ait sipariş numaralarını tahmin etmeye çalışıyorsa
    (örn. ORD-1001, ORD-1002, ORD-1003...), belirli bir eşik (threshold) aşıldığında sistem
    otomatik olarak 'enumeration_suspected' güvenlik alarmı üretir.

    Özellikler:
    - Kayan Zaman Penceresi: Belirlenen pencere süresinden (örn. 60 sn) eski denemeler otomatik silinir.
    - Alarm Seli Koruması: Eşik aşıldığında pencere süresince yalnızca BİR kez True döner (spam alarm önlenir).
    - Bellek Sınırı: En fazla 10.000 aktif kullanıcı hafızada tutulur (bellek şişirme saldırılarına karşı koruma).
    """

    _MAX_TRACKED_USERS = 10_000

    def __init__(
        self,
        threshold: int,
        window_sec: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = threshold
        self._window_sec = window_sec
        self._clock = clock
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = {}
        self._alerted_until: dict[str, float] = {}

    def record(self, user_id: str) -> bool:
        """Kullanıcının reddedilen bir erişimini kaydeder. Eşik aşıldıysa True döner."""
        with self._lock:
            now = self._clock()

            # Bellek taşması koruması: Tablo aşırı büyürse önce süresi dolmuş kayıtları temizle,
            # hala doluysa en eski girdiyi tahliye et (tüm tabloyu sıfırlayarak başkalarının sayacını silme DoS'unu önle).
            if len(self._events) >= self._MAX_TRACKED_USERS and user_id not in self._events:
                cutoff = now - self._window_sec
                expired_users = [
                    u for u, q in self._events.items()
                    if not q or q[-1] < cutoff
                ]
                for u in expired_users:
                    self._events.pop(u, None)
                    self._alerted_until.pop(u, None)

                while len(self._events) >= self._MAX_TRACKED_USERS:
                    oldest_user = next(iter(self._events))
                    self._events.pop(oldest_user, None)
                    self._alerted_until.pop(oldest_user, None)

            # Kullanıcının ret zaman damgalarını tutan kuyruğu al
            stamps = self._events.setdefault(user_id, deque())
            stamps.append(now)

            # Kayan zaman penceresinin dışına çıkan eski kayıtları kuyruktan temizle
            cutoff = now - self._window_sec
            while stamps and stamps[0] < cutoff:
                stamps.popleft()

            # Eşik aşıldı mı ve bu pencere içinde daha önce alarm üretilmedi mi?
            if len(stamps) >= self._threshold and self._alerted_until.get(user_id, 0.0) <= now:
                # Belirtilen pencere süresince bir daha mükerrer alarm üretilmesini engelle
                self._alerted_until[user_id] = now + self._window_sec
                return True

            return False


# Geriye dönük uyumluluk için takma ad (alias)
DenyTracker = InMemoryDenyTracker


RECORD_DENIED_LUA_SCRIPT = """
local window_key = KEYS[1]
local alerted_key = KEYS[2]
local now = tonumber(ARGV[1])
local cutoff = tonumber(ARGV[2])
local threshold = tonumber(ARGV[3])
local ttl = math.ceil(tonumber(ARGV[4]))
local member_id = ARGV[5]

redis.call('ZREMRANGEBYSCORE', window_key, '-inf', cutoff)
redis.call('ZADD', window_key, now, member_id)
redis.call('EXPIRE', window_key, ttl)

local count = redis.call('ZCARD', window_key)
if count >= threshold then
    local alerted_until = tonumber(redis.call('GET', alerted_key) or '0')
    if alerted_until <= now then
        local next_alert = now + tonumber(ARGV[4])
        redis.call('SET', alerted_key, tostring(next_alert), 'EX', ttl)
        return 1
    end
end
return 0
"""


class RedisDenyTracker:
    """Redis tabanlı dağıtık DenyTracker (Distributed Sliding Window).

    Amaç:
    Birden fazla instance çalıştığında (N instance), saldırganın farklı instance'lara
    dağılan istekleri tek bir Redis Sorted Set üzerinde birikir. Böylece eşik
    fiilen N katına çıkmaz; sistem genelinde kesin olarak 'threshold' değeri aşıldığında
    'enumeration_suspected' alarmı üretilir.
    """

    def __init__(
        self,
        redis_client: Any,
        threshold: int,
        window_sec: float,
        clock: Callable[[], float] = time.time,
        circuit_cooldown_sec: float = 30.0,
    ) -> None:
        self._redis = redis_client
        self._threshold = threshold
        self._window_sec = window_sec
        self._clock = clock
        self._circuit_cooldown_sec = circuit_cooldown_sec
        self._circuit_open_until = 0.0
        self._local_fallback = InMemoryDenyTracker(threshold, window_sec, clock=clock)

    def record(self, user_id: str) -> bool:
        """Kullanıcının reddedilen erişimini Redis'e kaydeder. Eşik aşıldıysa True döner."""
        now = self._clock()

        # Devre kesici (Circuit Breaker): Redis daha önce hata verdiyse cooldown süresince
        # Redis soketini bloklamadan doğrudan yerel InMemory depoya yönlendir
        if now < self._circuit_open_until:
            return self._local_fallback.record(user_id)

        cutoff = now - self._window_sec
        member_id = f"{now:.6f}:{uuid.uuid4().hex[:8]}"
        # Redis Cluster uyumluluğu için {user_id} hash tag kullanılır.
        # Bu sayede hem window_key hem de alerted_key aynı hash slot'a düşer (CROSSSLOT önlenir).
        window_key = f"audit:deny:{{{user_id}}}:window"
        alerted_key = f"audit:deny:{{{user_id}}}:alerted"

        try:
            res = self._redis.eval(
                RECORD_DENIED_LUA_SCRIPT,
                2,
                window_key,
                alerted_key,
                str(now),
                str(cutoff),
                str(self._threshold),
                str(self._window_sec),
                member_id,
            )
            self._circuit_open_until = 0.0
            return bool(res == 1 or res == b"1")
        except Exception as exc:
            self._circuit_open_until = now + self._circuit_cooldown_sec
            logger.warning(
                "RedisDenyTracker hatası (devre %.1f sn açık kalacak), InMemory depoya dönülüyor: %s",
                self._circuit_cooldown_sec,
                exc,
            )
            write_audit(
                "deny_tracker_circuit_opened",
                user_id=user_id,
                correlation_id=None,
                outcome="fallback_in_memory",
                cooldown_sec=self._circuit_cooldown_sec,
            )
            return self._local_fallback.record(user_id)


# Süreç genelinde tekil (singleton) DenyTracker örneği
_deny_tracker: Any | None = None


def get_deny_tracker() -> Any:
    """Konfigürasyon ayarlarından beslenen tekil DenyTracker nesnesini döner."""
    global _deny_tracker
    if _deny_tracker is None:
        from app.core.config import settings

        _deny_tracker = InMemoryDenyTracker(settings.AUDIT_DENY_THRESHOLD, settings.AUDIT_DENY_WINDOW_SEC)
    return _deny_tracker


def set_deny_tracker(tracker: Any) -> None:
    """DenyTracker nesnesini çalışma zamanında değiştirir (örn. Redis entegrasyonu veya testler)."""
    global _deny_tracker
    _deny_tracker = tracker


async def record_denied_access(user_id: str, correlation_id: str | None) -> None:
    """Yetkisiz/reddedilen erişimi sayaçta işler; eşik aşılmışsa 'enumeration_suspected' alarmı basar."""
    try:
        from app.core.config import settings

        tracker = get_deny_tracker()
        triggered = await asyncio.to_thread(tracker.record, user_id)
        if triggered:
            write_audit(
                "enumeration_suspected",
                user_id=user_id,
                correlation_id=correlation_id,
                outcome="alert",
                threshold=settings.AUDIT_DENY_THRESHOLD,
                window_sec=settings.AUDIT_DENY_WINDOW_SEC,
            )
    except Exception as exc:
        logger.warning("record_denied_access hatası: %s", type(exc).__name__)
