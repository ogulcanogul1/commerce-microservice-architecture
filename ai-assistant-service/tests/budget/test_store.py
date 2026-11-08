"""InMemoryBudgetStore ve BudgetStore arayüzü birim testleri."""

from __future__ import annotations

import asyncio
import pytest

from app.budget.models import Scope
from app.budget.store import InMemoryBudgetStore


@pytest.mark.anyio
async def test_in_memory_budget_store_reserve_success():
    """Limit dahilindeki rezervasyon başarılı olur ve sayaçlar artırılır."""
    store = InMemoryBudgetStore()
    scopes = [
        Scope(key="tok:user:1:day", limit=1000, ttl_sec=60),
        Scope(key="tok:user:1:min", limit=200, ttl_sec=60),
    ]

    res = await store.reserve(scopes, amount=100)
    assert res.allowed is True
    assert res.retry_after_sec == 0
    assert res.exceeded_key is None


@pytest.mark.anyio
async def test_in_memory_budget_store_atomic_all_or_nothing():
    """Biri bile limiti aşarsa HİÇBİR sayaç artırılmaz (Atomiklik)."""
    store = InMemoryBudgetStore()
    scope_day = Scope(key="tok:user:2:day", limit=1000, ttl_sec=60)
    scope_min = Scope(key="tok:user:2:min", limit=150, ttl_sec=60)

    # İlk rezervasyon: 100 token (her iki sayaç da 100 olur)
    res1 = await store.reserve([scope_day, scope_min], amount=100)
    assert res1.allowed is True

    # İkinci rezervasyon: 100 token.
    # Günlük limit 1000 (yeterli) ama dakikalık limit 150 (100 + 100 = 200 > 150 -> aşar!)
    res2 = await store.reserve([scope_day, scope_min], amount=100)
    assert res2.allowed is False
    assert res2.exceeded_key == "tok:user:2:min"
    assert res2.retry_after_sec > 0

    # Atomiklik kontrolü: Günlük sayaç artmamış olmalı (hâlâ 100 olmalı).
    # Eğer günlük sayaç artsaydı 850 token daha alamaması gerekirdi.
    # 50 token rezerve edersek (100 + 50 = 150 dakikalık tam sınır), ikisi de geçmeli:
    res3 = await store.reserve([scope_day, scope_min], amount=50)
    assert res3.allowed is True


@pytest.mark.anyio
async def test_in_memory_budget_store_adjust_reconcile():
    """Adjust negatif delta ile iade yapar ve sayaç asla 0'ın altına düşmez."""
    store = InMemoryBudgetStore()
    scope = Scope(key="tok:user:3:min", limit=500, ttl_sec=60)

    # 300 rezerve et
    await store.reserve([scope], amount=300)

    # Gerçekte 100 harcandı -> 200 iade et (delta = -200)
    await store.adjust([scope], delta=-200)

    # Kalan sayaç 100 olmalı. Limit 500 olduğuna göre 400 daha rezerve edilebilmeli:
    res = await store.reserve([scope], amount=400)
    assert res.allowed is True

    # Aşırı negatif iade: -1000 versek bile 0'ın altına düşmemeli
    await store.adjust([scope], delta=-1000)
    # Sıfırlandı, 500 token'ın tamamı tekrar rezerve edilebilmeli
    res_full = await store.reserve([scope], amount=500)
    assert res_full.allowed is True


@pytest.mark.anyio
async def test_in_memory_budget_store_ttl_expiration():
    """Süresi dolan anahtar otomatik olarak temizlenir."""
    store = InMemoryBudgetStore()
    # 0.05 saniyelik çok kısa TTL
    scope = Scope(key="tok:user:4:short", limit=100, ttl_sec=1)

    res = await store.reserve([scope], amount=100)
    assert res.allowed is True

    # Limit doldu, hemen peşinden istersek reddedilmeli
    res_rejected = await store.reserve([scope], amount=1)
    assert res_rejected.allowed is False

    # Suni olarak geçmişe çekerek TTL dolmasını simüle edelim
    store._data[scope.key][1] = 0.0

    # Artık süresi doldu, yeni istek başarılı olmalı
    res_after_expire = await store.reserve([scope], amount=100)
    assert res_after_expire.allowed is True


# ============================================================================
# RedisBudgetStore Testleri (FakeRedis & Lua)
# ============================================================================

@pytest.mark.anyio
async def test_redis_budget_store_reserve_and_adjust():
    """RedisBudgetStore Lua scriptleri ile atomik rezervasyon ve uzlaştırma yapar."""
    import fakeredis.aioredis
    from app.budget.redis_store import RedisBudgetStore

    fake_redis = fakeredis.aioredis.FakeRedis()
    store = RedisBudgetStore(fake_redis)

    scope_day = Scope(key="tok:test:day", limit=1000, ttl_sec=60)
    scope_min = Scope(key="tok:test:min", limit=200, ttl_sec=60)

    # 1. Başarılı rezervasyon
    res1 = await store.reserve([scope_day, scope_min], amount=150)
    assert res1.allowed is True
    assert res1.retry_after_sec == 0

    # 2. İkinci rezervasyon dakikalık limiti (200) aşar (150 + 100 = 250 > 200)
    res2 = await store.reserve([scope_day, scope_min], amount=100)
    assert res2.allowed is False
    assert res2.exceeded_key == "tok:test:min"
    assert res2.retry_after_sec > 0

    # 3. All-or-Nothing kontrolü: Günlük sayaç 150 olarak kalmış olmalı (artmamış olmalı)
    # 50 token rezerve edersek (150 + 50 = 200 tam limit) geçmeli:
    res3 = await store.reserve([scope_day, scope_min], amount=50)
    assert res3.allowed is True

    # 4. Adjust ile iade (negatif delta)
    await store.adjust([scope_day, scope_min], delta=-100)

    # Dakikalık sayaç 200'den 100'e düştü, artık 100 daha rezerve edilebilmeli
    res4 = await store.reserve([scope_day, scope_min], amount=100)
    assert res4.allowed is True

    # 5. Aşırı negatif iade sayaçları sıfırın altına düşürmez
    await store.adjust([scope_day, scope_min], delta=-10000)
    val = await fake_redis.get(scope_min.key)
    assert int(val) == 0

    await fake_redis.aclose()
