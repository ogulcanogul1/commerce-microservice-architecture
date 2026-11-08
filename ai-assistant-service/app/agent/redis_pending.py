"""Redis tabanlı kalıcı ve dağıtık bekleyen eylem deposu (RedisPendingActionStore).

Dağıtık Sistem ve Güvenlik İlkeleri:
1. Birden Fazla Replika Desteği: Kullanıcı A konteynerinde aksiyon üretip B konteynerinde onaylayabilir.
2. Atomik Çift Tıklama ve Tekrar Koruması: Aynı kullanıcı, aynı aksiyon türü ve aynı parametreler için
   halihazırda onay bekleyen bir aksiyon varsa mevcut olanı döner; gereksiz kopya oluşturmaz.
3. Atomik Tüketme (Consume) ve Sahiplik Doğrulama: Tek bir Lua script'i ile aksiyon tek kullanımlık olarak
   tüketilir (DEL) ve sahiplik doğrulanır. Başka kullanıcılar veriyi silemez.
4. Kesin Hata Yayılımı: Redis bağlantı hatalarında veri kaybını gizlememek için PendingActionStoreError fırlatır.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any

import redis
from redis.exceptions import RedisError

from app.agent.models import PendingAction
from app.agent.pending import PendingActionStore, PendingActionStoreError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LUA SCRIPT 1: Atomik Oluşturma veya Mevcut Olanı Döndürme (Create or Dedup)
# ---------------------------------------------------------------------------
# Amaç:
# Modelin aynı işlemi mükerrer teklif etmesi veya kullanıcının hızlıca çift tıklaması
# durumunda, aynı parametrelerle bekleyen aktif bir kayıt varsa mevcut olanı geri döndürür.
#
# Argümanlar:
# KEYS[1]: Dedup indeks anahtarı (Örn: 'pending:idx:user123:cancel_order:<hash>')
# KEYS[2]: Yeni aksiyon anahtarı (Örn: 'pending:act_c79bf20a...')
# ARGV[1]: JSON formatındaki yeni aksiyon verisi (payload)
# ARGV[2]: Kalan süre saniye (TTL)
# ARGV[3]: Yeni aksiyonun ID'si
# ARGV[4]: Anahtar öneki (prefix, örn: 'pending:')
CREATE_OR_GET_LUA_SCRIPT = """
-- 1. ADIM: Dedup indeksini kontrol et
local existing_id = redis.call('GET', KEYS[1])
if existing_id then
  local existing_key = ARGV[4] .. existing_id
  local existing_data = redis.call('GET', existing_key)
  if existing_data then
    -- Halihazırda bekleyen aktif bir onay talebi var, eskisini döndür
    return existing_data
  end
end

-- 2. ADIM: Aktif kayıt yoksa yeni kaydı ve indeksini kaydet
redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[2])
redis.call('SET', KEYS[1], ARGV[3], 'EX', ARGV[2])
return ARGV[1]
"""

# ---------------------------------------------------------------------------
# LUA SCRIPT 2: Atomik Tüketme (Consume) Script'i
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
  return nil
end

-- 3. ADIM: Sahiplik Güvenlik Kontrolü (Cross-User Security)
local owner = string.lower(obj['user_id'] or '')
local caller = ARGV[1]

if owner ~= caller then
  -- Başka bir kullanıcının aksiyonu; silme, yalnızca nil dön
  return nil
end

-- 4. ADIM: Tek Kullanımlık Tüketim (Atomik Pop)
redis.call('DEL', KEYS[1])
return data
"""

# ---------------------------------------------------------------------------
# LUA SCRIPT 3: Atomik İptal/Reddetme (Discard) Script'i
# ---------------------------------------------------------------------------
# Amaç:
# Kullanıcı "İptal Et" (Reject) dediğinde yalnızca gerçek sahibin aksiyonu silebilmesini sağlamak.
# Başarılı silmede JSON verisini döndürür ki Python tarafı dedup indeksini temizleyebilsin.
#
# Argümanlar:
# KEYS[1]: Redis anahtarı
# ARGV[1]: İptal etmek isteyen kullanıcının ID'si
DISCARD_LUA_SCRIPT = """
local data = redis.call('GET', KEYS[1])
if not data then
  return nil
end

local ok, obj = pcall(cjson.decode, data)
if not ok or not obj then
  return nil
end

local owner = string.lower(obj['user_id'] or '')
local caller = ARGV[1]

-- Sahiplik eşleşmiyorsa silme, nil dön
if owner ~= caller then
  return nil
end

-- Gerçek sahibi iptal ediyor, anahtarı sil ve silinen JSON'ı dön
redis.call('DEL', KEYS[1])
return data
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

    @staticmethod
    def _hash_params(params: dict[str, Any]) -> str:
        """Parametre sözlüğünü belirleyici (deterministik) sha256 özetine dönüştürür."""
        serialized = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _make_idx_key(self, user_id: str, action_type: str, params_hash: str) -> str:
        """Kullanıcı, aksiyon türü ve parametre özetinden dedup indeks anahtarı üretir."""
        normalized_user = str(user_id).strip().lower()
        return f"{self._prefix}idx:{normalized_user}:{action_type}:{params_hash}"

    def create(self, action: PendingAction) -> PendingAction:
        """Yeni bir bekleyen aksiyonu Redis'e kaydeder.
        
        Aynı kullanıcı + aynı eylem türü + aynı parametrelerle bekleyen aktif bir kayıt varsa,
        mükerrer kayıt açmak yerine mevcut olanı döndürür (Idempotency).
        """
        now = self._clock()
        remaining_sec = max(1, int((action.expires_at - now).total_seconds()))
        key = self._make_key(action.action_id)
        params_hash = self._hash_params(action.params)
        idx_key = self._make_idx_key(action.user_id, action.action_type, params_hash)

        try:
            payload = action.model_dump_json()
            raw_data = self._redis.eval(
                CREATE_OR_GET_LUA_SCRIPT,
                2,
                idx_key,
                key,
                payload,
                remaining_sec,
                action.action_id,
                self._prefix,
            )
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
            return PendingAction.model_validate_json(raw_data)
        except RedisError as exc:
            logger.exception("Redis pending action create hatası: %s", type(exc).__name__)
            raise PendingActionStoreError("Failed to store pending action in Redis") from exc

    def consume(self, action_id: str, user_id: str) -> PendingAction | None:
        """Atomik Lua script'i ile aksiyonu doğrular, Redis'ten siler ve döner."""
        key = self._make_key(action_id)
        normalized_caller = str(user_id).strip().lower()

        try:
            raw_data = self._redis.eval(CONSUME_LUA_SCRIPT, 1, key, normalized_caller)
            if not raw_data:
                return None

            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
            action = PendingAction.model_validate_json(raw_data)

            # Tüketilen aksiyonun dedup indeksini de temizle
            try:
                params_hash = self._hash_params(action.params)
                idx_key = self._make_idx_key(action.user_id, action.action_type, params_hash)
                self._redis.delete(idx_key)
            except Exception:
                pass

            return action
        except RedisError as exc:
            logger.exception("Redis pending action consume hatası: %s", type(exc).__name__)
            raise PendingActionStoreError("Failed to consume pending action from Redis") from exc

    def discard(self, action_id: str, user_id: str) -> bool:
        """Kullanıcının bekleyen aksiyonunu sahiplik kontrolüyle Redis'ten siler."""
        key = self._make_key(action_id)
        normalized_caller = str(user_id).strip().lower()

        try:
            raw_data = self._redis.eval(DISCARD_LUA_SCRIPT, 1, key, normalized_caller)
            if not raw_data:
                return False

            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
            action = PendingAction.model_validate_json(raw_data)

            try:
                params_hash = self._hash_params(action.params)
                idx_key = self._make_idx_key(action.user_id, action.action_type, params_hash)
                self._redis.delete(idx_key)
            except Exception:
                pass

            return True
        except RedisError as exc:
            logger.exception("Redis pending action discard hatası: %s", type(exc).__name__)
            raise PendingActionStoreError("Failed to discard pending action from Redis") from exc

    def restore(self, action: PendingAction) -> None:
        """İşlem downstream serviste geçici bir hata aldığında (503), aksiyonu kalan süresiyle Redis'e geri yükler."""
        now = self._clock()
        remaining_sec = int((action.expires_at - now).total_seconds())

        if remaining_sec > 0:
            key = self._make_key(action.action_id)
            params_hash = self._hash_params(action.params)
            idx_key = self._make_idx_key(action.user_id, action.action_type, params_hash)
            payload = action.model_dump_json()
            try:
                pipeline = self._redis.pipeline()
                pipeline.set(key, payload, ex=remaining_sec)
                pipeline.set(idx_key, action.action_id, ex=remaining_sec)
                pipeline.execute()
            except RedisError as exc:
                logger.exception("Redis pending action restore hatası: %s", type(exc).__name__)
                raise PendingActionStoreError("Failed to restore pending action in Redis") from exc
