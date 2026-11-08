"""Redis tabanlı kalıcı ve dağıtık bekleyen eylem deposu (RedisPendingActionStore).

Dağıtık Sistem ve Güvenlik İlkeleri:
1. Birden Fazla Replika Desteği: Kullanıcı A konteynerinde aksiyon üretip B konteynerinde onaylayabilir.
2. Atomik Çift Tıklama Koruması: Aynı anda gelen 2 onay isteğinde, tek bir Lua script'i ile aksiyon anında silinir (DEL),
   böylece sipariş asla 2 kez iptal edilmez.
3. Kullanıcı İzolasyonu: Bir kullanıcı başka bir kullanıcının aksiyon ID'sini tahmin edip onaylamaya kalkarsa,
   Lua script'i sahiplik uyuşmazlığında veriyi ASLA silmez ve işlemi reddeder.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
import logging
from typing import Any

import redis
from redis.exceptions import RedisError

from app.agent.models import PendingAction
from app.agent.pending import PendingActionStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LUA SCRIPT 1: Atomik Tüketme (Consume) Script'i
# ---------------------------------------------------------------------------
# Amaç:
# Aksiyonu oku, sahiplik (user_id) kontrolü yap ve TEK KULLANIMLIK olduğu için
# ANINDA SİL (DEL). Bunların hepsi tek bir atomik adımda gerçekleşir.
#
# Argümanlar:
# KEYS[1]: Redis anahtarı (Örn: 'pending:act_c79bf20a...')
# ARGV[1]: İşlemi onaylamak isteyen kullanıcının ID'si (Küçük harfe çevrilmiş)
CONSUME_LUA_SCRIPT = """
-- 1. ADIM: Redis'ten JSON verisini çek
local data = redis.call('GET', KEYS[1])

-- Eğer anahtar yoksa (hiç oluşmadı, süresi dolup silindi veya daha önce onaylandı) nil dön
if not data then
  return nil
end

-- 2. ADIM: JSON verisini Lua tablosuna ayrıştır (decode)
local ok, obj = pcall(cjson.decode, data)
if not ok or not obj then
  -- Veri bozuksa güvenli şekilde nil dön
  return nil
end

-- 3. ADIM: Sahiplik Güvenlik Kontrolü (Cross-User Security)
-- Onaylamaya çalışan kullanıcı ile aksiyonun gerçek sahibi aynı mı?
local owner = string.lower(obj['user_id'] or '')
local caller = ARGV[1]

if owner ~= caller then
  -- DİKKAT: Başka bir kullanıcının aksiyonu!
  -- Güvenlik Kuralı: Kaydı SİLME! Çünkü gerçek sahibi daha sonra onaylayabilir. Yalnızca nil dön.
  return nil
end

-- 4. ADIM: Tek Kullanımlık Tüketim (Atomik Pop)
-- Doğrulama başarılı, bu aksiyonun ikinci kez çalıştırılmasını (replay attack)
-- önlemek için Redis'ten hemen SİL!
redis.call('DEL', KEYS[1])

-- Orijinal JSON verisini çağıran Python koduna teslim et
return data
"""

# ---------------------------------------------------------------------------
# LUA SCRIPT 2: Atomik İptal/Reddetme (Discard) Script'i
# ---------------------------------------------------------------------------
# Amaç:
# Kullanıcı "İptal Et" (Reject) dediğinde yalnızca gerçek sahibin aksiyonu silebilmesini sağlamak.
#
# Argümanlar:
# KEYS[1]: Redis anahtarı
# ARGV[1]: İptal etmek isteyen kullanıcının ID'si
DISCARD_LUA_SCRIPT = """
local data = redis.call('GET', KEYS[1])
if not data then
  return 0
end

local ok, obj = pcall(cjson.decode, data)
if not ok or not obj then
  return 0
end

local owner = string.lower(obj['user_id'] or '')
local caller = ARGV[1]

-- Sahiplik eşleşmiyorsa silme, 0 dön
if owner ~= caller then
  return 0
end

-- Gerçek sahibi iptal ediyor, anahtarı sil ve 1 (başarılı) dön
redis.call('DEL', KEYS[1])
return 1
"""


class RedisPendingActionStore(PendingActionStore):
    """PendingActionStore protokolünü implemente eden, Redis ve Lua script tabanlı dağıtık depo."""

    def __init__(
        self,
        redis_client: redis.Redis,
        clock: Callable[[], datetime] | None = None,
        key_prefix: str = "pending:",
    ) -> None:
        self._redis = redis_client
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._prefix = key_prefix

    def _make_key(self, action_id: str) -> str:
        """Aksiyon ID'sini Redis anahtarına çevirir (Örn: 'pending:act_123')."""
        return f"{self._prefix}{action_id}"

    def create(self, action: PendingAction) -> PendingAction:
        """Yeni bir bekleyen aksiyonu Redis'e TTL (Time-To-Live) süresiyle kaydeder."""
        now = self._clock()
        # Kalan saniye süresini hesapla (en az 1 saniye olmalı)
        remaining_sec = max(1, int((action.expires_at - now).total_seconds()))
        key = self._make_key(action.action_id)

        try:
            # JSON formatında ve otomatik silinme süresiyle (EX) Redis'e yaz
            payload = action.model_dump_json()
            self._redis.set(key, payload, ex=remaining_sec)
            return action
        except RedisError as exc:
            logger.warning("Redis pending action create hatası: %s", type(exc).__name__)
            # Redis patlasa bile uygulamanın çökmesini önlemek için nesneyi dön
            return action

    def consume(self, action_id: str, user_id: str) -> PendingAction | None:
        """Atomik Lua script'i ile aksiyonu doğrular, Redis'ten siler ve döner."""
        key = self._make_key(action_id)
        normalized_caller = str(user_id).strip().lower()

        try:
            # CONSUME_LUA_SCRIPT'i Redis motoru üzerinde atomik çalıştır
            raw_data = self._redis.eval(CONSUME_LUA_SCRIPT, 1, key, normalized_caller)
            if not raw_data:
                return None

            # String veriyi PendingAction Pydantic modeline dönüştür
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
            return PendingAction.model_validate_json(raw_data)
        except RedisError as exc:
            logger.warning("Redis pending action consume hatası: %s", type(exc).__name__)
            return None

    def discard(self, action_id: str, user_id: str) -> bool:
        """Kullanıcının bekleyen aksiyonunu sahiplik kontrolüyle Redis'ten siler."""
        key = self._make_key(action_id)
        normalized_caller = str(user_id).strip().lower()

        try:
            result = self._redis.eval(DISCARD_LUA_SCRIPT, 1, key, normalized_caller)
            return int(result or 0) == 1
        except RedisError as exc:
            logger.warning("Redis pending action discard hatası: %s", type(exc).__name__)
            return False

    def restore(self, action: PendingAction) -> None:
        """İşlem downstream serviste geçici bir hata aldığında (503), aksiyonu kalan süresiyle Redis'e geri yükler."""
        now = self._clock()
        remaining_sec = int((action.expires_at - now).total_seconds())

        # Eğer süresi henüz dolmadıysa Redis'e tekrar koy
        if remaining_sec > 0:
            key = self._make_key(action.action_id)
            try:
                payload = action.model_dump_json()
                self._redis.set(key, payload, ex=remaining_sec)
            except RedisError as exc:
                logger.warning("Redis pending action restore hatası: %s", type(exc).__name__)
