"""Redis tabanlı atomik token bütçesi deposu (RedisBudgetStore).

Dağıtık Sistem Mimarisi:
Birden fazla replika/container çalıştığında yarış koşullarını (Race Condition) engellemek
ve bütçe kontrolünü tek bir ağ çağrısında (Single Round-Trip) tamamlamak için
Redis sunucusu üzerinde atomik Lua script'leri çalıştırılır.
"""

from __future__ import annotations

from collections.abc import Sequence
import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.budget.models import ReserveResult, Scope
from app.budget.store import BudgetStore, BudgetStoreError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Atomik Rezervasyon Lua Script'i (All-or-Nothing Two-Phase Commit)
# ---------------------------------------------------------------------------
# KEYS: Kontrol edilecek Redis sayaç anahtarları
# ARGV[1]: Rezerve edilmek istenen token miktarı (amount)
# ARGV[2..N]: Her anahtar için sırasıyla (limit, ttl_saniye) ikilileri
RESERVE_LUA_SCRIPT = """
local amount = tonumber(ARGV[1])
local n = #KEYS

-- 1. AŞAMA: DOĞRULAMA (Verification)
-- Tüm anahtarları tek tek kontrol et; biri bile limiti aşarsa hiçbirini artırma!
for i = 1, n do
  local limit = tonumber(ARGV[2 * i])
  local cur = tonumber(redis.call('GET', KEYS[i]) or '0')
  if cur + amount > limit then
    local ttl = redis.call('TTL', KEYS[i])
    -- Ret dön: {izin_verildi_mi=0, asan_anahtar_indeksi=i, kalan_ttl_saniyesi=ttl}
    return {0, i, ttl}
  end
end

-- 2. AŞAMA: ÇALIŞTIRMA (Execution)
-- Tüm sayaçlar geçerli; hepsini atomik olarak 'amount' kadar artır
for i = 1, n do
  local ttl = tonumber(ARGV[2 * i + 1])
  local v = redis.call('INCRBY', KEYS[i], amount)
  -- Eğer anahtar ilk defa oluşturulduysa (değeri amount'a eşitse) TTL süresini tanımla
  if v == amount then
    redis.call('EXPIRE', KEYS[i], ttl)
  end
end

-- Başarılı: {izin_verildi_mi=1, asan_anahtar_indeksi=0, kalan_ttl_saniyesi=0}
return {1, 0, 0}
"""

# ---------------------------------------------------------------------------
# Atomik Uzlaştırma Lua Script'i (Reconciliation)
# ---------------------------------------------------------------------------
# KEYS: Düzeltilecek Redis sayaç anahtarları
# ARGV[1]: Eklenecek veya çıkarılacak miktar (delta)
ADJUST_LUA_SCRIPT = """
local delta = tonumber(ARGV[1])
local n = #KEYS

for i = 1, n do
  -- Anahtar mevcutsa değerini delta kadar değiştir
  if redis.call('EXISTS', KEYS[i]) == 1 then
    local val = redis.call('INCRBY', KEYS[i], delta)
    -- Dağıtık Sistem Kuralı: Bütçe sayacı asla 0'ın altına düşemez!
    if val < 0 then
      redis.call('SET', KEYS[i], 0, 'KEEPTTL')
    end
  end
end

return 1
"""


class RedisBudgetStore(BudgetStore):
    """BudgetStore arayüzünü uygulayan, Redis ve Lua script tabanlı dağıtık bütçe deposu."""

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def reserve(self, scopes: Sequence[Scope], amount: int) -> ReserveResult:
        """Tüm scope'ları tek bir atomik Lua script'i ile Redis üzerinde rezerve eder."""
        if not scopes:
            return ReserveResult(allowed=True, retry_after_sec=0)

        keys: list[str] = [sc.key for sc in scopes]
        # Lua argümanlarını hazırla: [amount, limit1, ttl1, limit2, ttl2, ...]
        argv: list[Any] = [amount]
        for sc in scopes:
            argv.append(sc.limit)
            argv.append(sc.ttl_sec)

        try:
            # Lua script'ini Redis sunucusunda çalıştır
            raw_res = await self._redis.eval(RESERVE_LUA_SCRIPT, len(keys), *keys, *argv)
        except RedisError as exc:
            # Loglara asla hassas anahtar veya token yazma, yalnızca hata türünü logla
            logger.warning("Redis bütçe rezervasyonu sırasında altyapı hatası: %s", type(exc).__name__)
            raise BudgetStoreError(f"Redis hatası: {type(exc).__name__}") from exc

        # Lua dönüşü: {allowed (0 veya 1), exceeded_index (1-based), ttl}
        allowed_flag = int(raw_res[0])
        exceeded_idx = int(raw_res[1])
        raw_ttl = int(raw_res[2])

        if allowed_flag == 1:
            return ReserveResult(allowed=True, retry_after_sec=0)

        # Hangi sayacın aştığını bul (Lua 1-based index kullanır, Python 0-based'e çevir)
        exceeded_key = None
        if 1 <= exceeded_idx <= len(scopes):
            exceeded_key = scopes[exceeded_idx - 1].key

        # TTL negatif dönerse (anahtar yok veya TTL set edilmemişse) scope'un varsayılan TTL'ini kullan
        retry_after = raw_ttl if raw_ttl > 0 else (scopes[exceeded_idx - 1].ttl_sec if exceeded_key else 1)

        return ReserveResult(
            allowed=False,
            retry_after_sec=max(1, retry_after),
            exceeded_key=exceeded_key,
        )

    async def adjust(self, scopes: Sequence[Scope], delta: int) -> None:
        """Gerçek kullanıma göre sayaçları atomik olarak düzeltir (iade veya ek harcama)."""
        if not scopes:
            return

        keys: list[str] = [sc.key for sc in scopes]
        try:
            await self._redis.eval(ADJUST_LUA_SCRIPT, len(keys), *keys, delta)
        except RedisError as exc:
            logger.warning("Redis bütçe uzlaştırması (adjust) sırasında altyapı hatası: %s", type(exc).__name__)
            raise BudgetStoreError(f"Redis hatası: {type(exc).__name__}") from exc
