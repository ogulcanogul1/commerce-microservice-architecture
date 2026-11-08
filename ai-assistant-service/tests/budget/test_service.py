"""TokenBudgetService ve Reservation yaşam döngüsü birim testleri."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest

from app.budget.deps import get_budget_subject
from app.budget.models import Scope
from app.budget.service import (
    BudgetUnavailable,
    Reservation,
    TokenBudgetExceeded,
    TokenBudgetService,
)
from app.budget.store import BudgetStoreError, InMemoryBudgetStore


# Sabit test saati: 2026-11-08 15:30:00 UTC (timestamp: 1794151800)
FIXED_NOW = datetime(2026, 11, 8, 15, 30, 0, tzinfo=timezone.utc)


def test_scopes_for_generation():
    """Doğru anahtar formatları ve provider scope oluşturulur."""
    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=50000,
        per_minute_limit=8000,
        provider_tpm_limit=100000,
        provider_name="gemini",
        clock=lambda: FIXED_NOW,
    )

    scopes = svc.scopes_for("user-123")
    assert len(scopes) == 3
    # 1. Günlük
    assert scopes[0].key == "tok:user:user-123:day:20261108"
    assert scopes[0].limit == 50000
    # 2. Dakikalık
    epoch_min = int(FIXED_NOW.timestamp() // 60)
    assert scopes[1].key == f"tok:user:user-123:min:{epoch_min}"
    assert scopes[1].limit == 8000
    # 3. Provider TPM
    assert scopes[2].key == f"tok:provider:gemini:min:{epoch_min}"
    assert scopes[2].limit == 100000


def test_scopes_for_without_provider():
    """provider_tpm_limit 0 iken 3. scope eklenmez."""
    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=50000,
        per_minute_limit=8000,
        provider_tpm_limit=0,
        clock=lambda: FIXED_NOW,
    )
    scopes = svc.scopes_for("anon")
    assert len(scopes) == 2


@pytest.mark.anyio
async def test_reservation_lifecycle_reconcile():
    """Başarılı işlemde fark iade edilir."""
    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=10000,
        per_minute_limit=2000,
        clock=lambda: FIXED_NOW,
    )

    # 1000 token rezerve et, gerçekte 600 harcansın
    async with await svc.reserve("user-abc", amount=1000) as res:
        res.record(600)

    # Rezerve 1000 edilmişti, 400 iade edildi -> şu an harcanan 600 olmalı.
    # Dakikalık limit 2000 olduğuna göre 1400 daha rezerve edilebilmeli:
    res2 = await svc.reserve("user-abc", amount=1400)
    assert res2.reserved == 1400


@pytest.mark.anyio
async def test_reservation_lifecycle_refunds_on_error():
    """İşlem hata fırlatırsa rezerve edilen miktarın tamamı iade edilir."""
    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=1000,
        per_minute_limit=1000,
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(RuntimeError):
        async with await svc.reserve("user-err", amount=800):
            raise RuntimeError("LLM çöktü!")

    # 800 token'ın tamamı iade edildiği için tekrar 1000 token rezerve edilebilmeli
    res_again = await svc.reserve("user-err", amount=1000)
    assert res_again.reserved == 1000


@pytest.mark.anyio
async def test_reservation_lifecycle_no_refund_on_timeout():
    """Zaman aşımında (TimeoutError) rezervasyon iade edilmez, harcanmış sayılır."""
    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=1000,
        per_minute_limit=1000,
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(TimeoutError):
        async with await svc.reserve("user-timeout", amount=800):
            raise TimeoutError("LLM çağrısı zaman aşımına uğradı")

    # 800 token iade edilmediği için kalan bütçe 200'dür; 500 daha isterse 429 almalı
    with pytest.raises(TokenBudgetExceeded):
        await svc.reserve("user-timeout", amount=500)


@pytest.mark.anyio
async def test_reservation_lifecycle_no_refund_on_asyncio_timeout():
    """Gerçek asyncio.timeout içinde zaman aşımına uğrayan rezervasyon iade edilmez."""
    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=1000,
        per_minute_limit=1000,
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(TimeoutError):
        async with await svc.reserve("user-async-to", amount=800):
            async with asyncio.timeout(0.01):
                await asyncio.sleep(0.1)

    # 800 token iade edilmedi, kalan bütçe 200; 500 daha isterse 429 almalı
    with pytest.raises(TokenBudgetExceeded):
        await svc.reserve("user-async-to", amount=500)


@pytest.mark.anyio
async def test_reservation_lifecycle_no_refund_on_cancelled_error():
    """CancelledError durumunda da (timeout sırasında iç görev iptali) rezervasyon iade edilmez."""
    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=1000,
        per_minute_limit=1000,
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(asyncio.CancelledError):
        async with await svc.reserve("user-cancel", amount=800):
            raise asyncio.CancelledError()

    with pytest.raises(TokenBudgetExceeded):
        await svc.reserve("user-cancel", amount=500)


@pytest.mark.anyio
async def test_reserve_exceeded_raises_429():
    """Bütçe dolduğunda TokenBudgetExceeded (429) fırlatılır."""
    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=500,
        per_minute_limit=500,
        clock=lambda: FIXED_NOW,
    )

    # 400 rezerve et
    await svc.reserve("user-limit", amount=400)

    # 200 daha isterse (400 + 200 = 600 > 500) 429 almalı
    with pytest.raises(TokenBudgetExceeded) as exc_info:
        await svc.reserve("user-limit", amount=200)

    assert exc_info.value.status_code == 429
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after_seconds > 0
    assert exc_info.value.headers.get("Retry-After") is not None


@pytest.mark.anyio
async def test_daily_token_budget_retry_after_capped_to_midnight():
    """Günlük kota dolduğunda Retry-After 48 saat değil, UTC gece yarısına kalan süre olmalıdır."""
    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=500,
        per_minute_limit=10000,
        clock=lambda: FIXED_NOW,
    )

    await svc.reserve("user-daily", amount=400)
    with pytest.raises(TokenBudgetExceeded) as exc_info:
        await svc.reserve("user-daily", amount=200)

    # FIXED_NOW = 15:30:00 UTC -> Gece yarısına (00:00:00 UTC) kalan süre: 8.5 saat = 30600 sn
    assert exc_info.value.retry_after_seconds == 30600
    assert exc_info.value.retry_after_seconds <= 86400
    assert exc_info.value.headers.get("Retry-After") == "30600"


@pytest.mark.anyio
async def test_minute_token_budget_retry_after_capped_to_next_minute():
    """Dakikalık burst kotası dolduğunda Retry-After bir sonraki dakikaya kalan süreyi aşamaz."""
    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=50000,
        per_minute_limit=500,
        clock=lambda: FIXED_NOW,
    )

    await svc.reserve("user-min", amount=400)
    with pytest.raises(TokenBudgetExceeded) as exc_info:
        await svc.reserve("user-min", amount=200)

    assert exc_info.value.retry_after_seconds <= 60
    assert exc_info.value.headers.get("Retry-After") is not None


@pytest.mark.anyio
async def test_store_error_fallback_mode_local():
    """Birincil store patlarsa fail_mode='local' iken fallback store devreye girer."""
    class FailingStore:
        async def reserve(self, scopes, amount):
            raise BudgetStoreError("Redis connection refused")
        async def adjust(self, scopes, delta):
            pass

    fallback = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=FailingStore(),  # type: ignore[arg-type]
        fallback_store=fallback,
        fail_mode="local",
        daily_limit=1000,
        per_minute_limit=1000,
        clock=lambda: FIXED_NOW,
    )

    # Fallback store sayesinde istek başarılı olmalı
    res = await svc.reserve("user-fb", amount=100)
    assert res.reserved == 100


@pytest.mark.anyio
async def test_store_error_fail_closed():
    """Birincil store patlarsa fail_mode='closed' iken BudgetUnavailable (503) fırlatılır."""
    class FailingStore:
        async def reserve(self, scopes, amount):
            raise BudgetStoreError("Redis connection refused")
        async def adjust(self, scopes, delta):
            pass

    svc = TokenBudgetService(
        store=FailingStore(),  # type: ignore[arg-type]
        fail_mode="closed",
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(BudgetUnavailable) as exc_info:
        await svc.reserve("user-closed", amount=100)

    assert exc_info.value.status_code == 503
    assert exc_info.value.retryable is True


def test_get_budget_subject():
    """UUID olan ve olmayan başlıklarda doğru subject üretilir."""
    # Geçerli UUID
    valid_uuid = "C0A80101-1234-5678-9ABC-DEF012345678"
    assert get_budget_subject(valid_uuid) == valid_uuid.lower()

    # None veya geçersiz string
    assert get_budget_subject(None) == "anonymous"
    assert get_budget_subject("not-a-uuid") == "anonymous"
    assert get_budget_subject("") == "anonymous"
