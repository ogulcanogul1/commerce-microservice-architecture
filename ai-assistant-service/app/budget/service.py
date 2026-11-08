"""Token bütçesi yönetim servisi ve Reserve & Reconcile yaşam döngüsü.

Mali Güvenlik Mantığı:
1. Rezerve Et (Reserve): LLM çağrılmadan önce tahmini token bütçeden peşinen ayrılır (429 Fast-Fail).
2. Çalıştır (Execute): LLM çağrısı yapılır ve asıl kullanılan token miktarı öğrenilir.
3. Uzlaştır (Reconcile / Adjust): Aradaki fark bütçeye iade edilir veya eklenir. Hata durumunda tamamı iade edilir.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import logging
from typing import Any, Literal

from app.budget.models import ReserveResult, Scope
from app.budget.store import BudgetStore, BudgetStoreError
from app.core.errors import ProblemType, RetryableException

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bütçe Özel HTTP İstisnaları (RFC 7807 Uyumlu)
# ---------------------------------------------------------------------------

class TokenBudgetExceeded(RetryableException):
    """Kullanıcının günlük veya dakikalık token kotası dolduğunda fırlatılan 429 istisnası."""

    def __init__(
        self,
        retry_after_seconds: int = 60,
        detail: str = "Kullanım kotanıza ulaştınız. Lütfen daha sonra tekrar deneyin.",
    ) -> None:
        super().__init__(
            status_code=429,
            detail=detail,
            problem_type=ProblemType.TOKEN_BUDGET_EXCEEDED,
            title="Too Many Requests",
            retry_after_seconds=max(1, retry_after_seconds),
        )


class BudgetUnavailable(RetryableException):
    """Bütçe veritabanı (Redis) çöktüğünde ve fail_mode='closed' iken fırlatılan 503 istisnası."""

    def __init__(
        self,
        detail: str = "Bütçe kontrol servisi geçici olarak kullanılamıyor. Lütfen kısa süre sonra tekrar deneyin.",
        retry_after_seconds: int = 5,
    ) -> None:
        super().__init__(
            status_code=503,
            detail=detail,
            problem_type=ProblemType.BUDGET_UNAVAILABLE,
            title="Service Unavailable",
            retry_after_seconds=retry_after_seconds,
        )


# ---------------------------------------------------------------------------
# Rezervasyon Context Manager (Reserve & Reconcile Yaşam Döngüsü)
# ---------------------------------------------------------------------------

class Reservation:
    """Tek bir isteğin token bütçe yaşam döngüsünü yöneten asenkron context manager.
    
    Kullanım:
        async with budget_service.reserve(user_id, estimated_tokens) as res:
            reply = await llm_call()
            res.record(reply.usage)
    """

    def __init__(
        self,
        store: BudgetStore,
        scopes: Sequence[Scope],
        reserved_amount: int,
    ) -> None:
        self._store = store
        self._scopes = scopes
        self.reserved: int = reserved_amount
        self.actual: int | None = None

    def record(self, usage: Any) -> None:
        """LLM'den dönen gerçek token kullanım bilgisini kaydeder.
        
        usage bir TokenUsage modeli (input_tokens + output_tokens) veya doğrudan bir tamsayı olabilir.
        """
        if usage is None:
            return

        if isinstance(usage, int):
            self.actual = max(0, usage)
        elif hasattr(usage, "input_tokens") and hasattr(usage, "output_tokens"):
            inp = getattr(usage, "input_tokens", 0) or 0
            out = getattr(usage, "output_tokens", 0) or 0
            self.actual = max(0, inp + out)
        elif hasattr(usage, "total_tokens"):
            self.actual = max(0, getattr(usage, "total_tokens", 0) or 0)

    async def __aenter__(self) -> Reservation:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """İşlem bittiğinde bütçe uzlaştırmasını (Reconciliation) otomatik yapar."""
        try:
            # 1. Durum: Zaman aşımı (TimeoutError veya CancelledError) durumu
            # Sağlayıcı tokenları işlemiş veya faturalamış olabileceğinden ve kötüye kullanımı (sürekli timeout'a
            # sokarak sınırsız istek deneme) engellemek için, zaman aşımında rezervasyon iade edilmez (kotadan harcanır).
            # Eğer kısmi gerçek harcama bildirildiyse o uzlaştırılır, bildirilmediyse rezervasyon harcanmış sayılır.
            if isinstance(exc_val, (TimeoutError, asyncio.TimeoutError, asyncio.CancelledError)):
                if self.actual is not None:
                    delta = self.actual - self.reserved
                    await self._store.adjust(self._scopes, delta)
                return

            # 2. Durum: İstek sırasında diğer bir hata fırlatıldıysa (Bağlantı hatası, doğrulama vb.)
            # -> Rezerve edilen miktarın TAMAMINI iade et!
            if exc_val is not None:
                await self._store.adjust(self._scopes, -self.reserved)
                return

            # 3. Durum: İşlem başarılı bitti ve gerçek harcama bildirildi -> Aradaki farkı uzlaştır
            if self.actual is not None:
                delta = self.actual - self.reserved
                # delta negatifse iade yapılır, pozitifse ek bütçe düşülür
                await self._store.adjust(self._scopes, delta)

            # 4. Durum: actual bildirilmediyse rezervasyon olduğu gibi kalır

        except Exception as exc:
            # Kritik Kural: Bütçe uzlaştırma hatası (Redis timeout vb.) başarılı dönmüş isteği ASLA bozmamalıdır!
            # Yalnızca uyarı loglanır, kullanıcıya hata yansıtılmaz.
            logger.warning(
                "Bütçe uzlaştırması (adjust) sırasında altyapı uyarısı: %s",
                type(exc).__name__,
            )


# ---------------------------------------------------------------------------
# Token Bütçesi Servisi (TokenBudgetService)
# ---------------------------------------------------------------------------

class TokenBudgetService:
    """Tüm token bütçesi mantığını, scope oluşturmayı ve fallback mekanizmasını yöneten servis."""

    def __init__(
        self,
        store: BudgetStore,
        fallback_store: BudgetStore | None = None,
        *,
        daily_limit: int = 50000,
        per_minute_limit: int = 8000,
        provider_tpm_limit: int = 0,
        provider_name: str = "gemini",
        fail_mode: Literal["local", "closed"] = "local",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._fallback_store = fallback_store
        self.daily_limit = daily_limit
        self.per_minute_limit = per_minute_limit
        self.provider_tpm_limit = provider_tpm_limit
        self.provider_name = provider_name
        self.fail_mode = fail_mode  # 'local' (bellek içi yedek) veya 'closed' (503 fail-closed)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def scopes_for(self, subject: str) -> list[Scope]:
        """Kullanıcı kimliği (subject) ve geçerli zamana göre kontrol edilecek scope listesini üretir."""
        now = self._clock()
        # Gün formatı: 20261108
        day_str = now.strftime("%Y%m%d")
        # Dakika formatı: Unix timestamp'in dakika tamsayı değeri (Epoch Minute)
        epoch_minute = int(now.timestamp() // 60)

        scopes = [
            # 1. Kullanıcı Günlük Kotası (TTL: 48 saat = 172800s)
            Scope(
                key=f"tok:user:{subject}:day:{day_str}",
                limit=self.daily_limit,
                ttl_sec=172800,
            ),
            # 2. Kullanıcı Dakikalık Burst Kotası (TTL: 2 dakika = 120s)
            Scope(
                key=f"tok:user:{subject}:min:{epoch_minute}",
                limit=self.per_minute_limit,
                ttl_sec=120,
            ),
        ]

        # 3. Tüm Sunucuların Ortak Sağlayıcı TPM Kotası (Aktifse: provider_tpm_limit > 0)
        if self.provider_tpm_limit > 0:
            scopes.append(
                Scope(
                    key=f"tok:provider:{self.provider_name}:min:{epoch_minute}",
                    limit=self.provider_tpm_limit,
                    ttl_sec=120,
                )
            )

        return scopes

    async def reserve(self, subject: str, amount: int) -> Reservation:
        """Kullanıcı için peşinen token rezerve eder ve Reservation context manager döner."""
        scopes = self.scopes_for(subject)
        active_store = self._store

        try:
            result = await self._store.reserve(scopes, amount)
        except BudgetStoreError as exc:
            # Redis çöktüyse fail_mode stratejisine göre karar ver
            if self.fail_mode == "local" and self._fallback_store is not None:
                logger.warning(
                    "Birincil bütçe deposu arızalandı (%s), yerel InMemory depoya geçiliyor.",
                    type(exc).__name__,
                )
                active_store = self._fallback_store
                result = await self._fallback_store.reserve(scopes, amount)
            else:
                logger.error("Bütçe deposu erişilemez durumda (fail_mode=%s)", self.fail_mode)
                raise BudgetUnavailable() from exc

        # Kota aşıldıysa anında 429 fırlat
        if not result.allowed:
            logger.info(
                "Kullanıcı token bütçesi aşıldı (retry_after=%ds)",
                result.retry_after_sec,
            )
            raise TokenBudgetExceeded(retry_after_seconds=result.retry_after_sec)

        # Rezervasyon başarılı, çağıranın 'async with' ile kullanabileceği nesneyi dön
        return Reservation(
            store=active_store,
            scopes=scopes,
            reserved_amount=amount,
        )
