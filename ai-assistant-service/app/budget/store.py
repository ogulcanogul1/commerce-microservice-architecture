"""Token bütçesi depolama arayüzü (Interface / ABC) ve bellek içi implementasyonu.

Dağıtık Sistem İlkesi (Atomiklik - All-or-Nothing):
Bir istek geldiğinde birden fazla scope (günlük limit, dakikalık limit, sağlayıcı limiti)
aynı anda kontrol edilir. Biri bile aşarsa HİÇBİR sayaç artırılmaz.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Sequence
import time

from app.budget.models import ReserveResult, Scope


class BudgetStoreError(Exception):
    """Bütçe deposuyla (Redis vb.) iletişimde veya işlem yürütülürken oluşan altyapı hatası."""


class BudgetStore(ABC):
    """Token bütçesi sayaçlarını yöneten temel arayüz (Interface).
    
    Tüm bütçe depolama sınıfları (InMemoryBudgetStore, RedisBudgetStore)
    bu arayüzü implemente etmek zorundadır.
    """

    @abstractmethod
    async def reserve(self, scopes: Sequence[Scope], amount: int) -> ReserveResult:
        """Belirtilen tüm scope'larda atomik olarak token rezerve eder.
        
        Kural (All-or-Nothing):
        Eğer tüm scope'larda (mevcut + amount <= limit) sağlanıyorsa hepsi artırılır.
        Herhangi biri limiti aşarsa HİÇBİR sayaç artırılmaz ve ret (allowed=False) döner.
        """
        ...

    @abstractmethod
    async def adjust(self, scopes: Sequence[Scope], delta: int) -> None:
        """Gerçek kullanım ile rezerve edilen miktar arasındaki farkı telafi eder (Reconciliation).
        
        - delta pozitif ise: Tahminden fazla harcanmıştır, bütçeden ek düşülür.
        - delta negatif ise: Tahminden az harcanmıştır veya istek çökmüştür, fark iade edilir.
        Kural: Sayaç değeri hiçbir zaman 0'ın altına düşemez.
        """
        ...


class InMemoryBudgetStore(BudgetStore):
    """BudgetStore arayüzünü implemente eden bellek içi (In-Memory) depo.
    
    Tek süreçli ortamlar, birim testler ve Redis arızasında yerel yedek (Fallback) için kullanılır.
    asyncio.Lock ile asenkron fonksiyonlar arasında yarış koşullarını (Race Condition) önler.
    """

    def __init__(self) -> None:
        # Anahtar formatı -> [mevcut_harcanan_token (float), son_kullanma_zamani_epoch (float)]
        self._data: dict[str, list[float]] = {}
        # Aynı anda çalışan asenkron görevlerin sözlüğü bozmasını önleyen kilit
        self._lock = asyncio.Lock()

    def _cleanup_expired(self, key: str, now: float) -> None:
        """Süresi (TTL) dolmuş anahtarı bellekten siler (Lazy Eviction)."""
        if key in self._data:
            _, expires_at = self._data[key]
            # Eğer şu anki zaman, son kullanma tarihini geçtiyse anahtarı temizle
            if now >= expires_at:
                del self._data[key]

    async def reserve(self, scopes: Sequence[Scope], amount: int) -> ReserveResult:
        """Tüm scope'lar için atomik rezervasyon kontrolü yapar."""
        now = time.time()

        async with self._lock:
            # 1. Adım: Süresi dolmuş olan sayaçları hafızadan temizle
            for sc in scopes:
                self._cleanup_expired(sc.key, now)

            # 2. Adım: DOĞRULAMA (Verification Phase)
            # Tüm sayaçları kontrol et: Herhangi biri limiti aşıyor mu?
            for sc in scopes:
                current_val = int(self._data[sc.key][0]) if sc.key in self._data else 0
                if current_val + amount > sc.limit:
                    # Bütçe aşıldı! Bu sayacın sıfırlanmasına kaç saniye kaldığını hesapla
                    if sc.key in self._data:
                        remaining_ttl = max(1, int(self._data[sc.key][1] - now))
                    else:
                        remaining_ttl = sc.ttl_sec

                    # Atomiklik gereği: Diğer sayaçlara hiç dokunmadan hemen ret dönüyoruz
                    return ReserveResult(
                        allowed=False,
                        retry_after_sec=remaining_ttl,
                        exceeded_key=sc.key,
                    )

            # 3. Adım: ÇALIŞTIRMA (Execution Phase)
            # Tüm sayaçlar limiti karşılıyor, şimdi hepsini atomik olarak 'amount' kadar artır
            for sc in scopes:
                if sc.key in self._data:
                    # Var olan sayacı artır (mevcut TTL süresini koru)
                    self._data[sc.key][0] += amount
                else:
                    # Yeni sayaç oluştur: [harcanan_miktar, son_kullanma_zamani]
                    self._data[sc.key] = [float(amount), now + sc.ttl_sec]

            # Rezervasyon başarıyla tamamlandı
            return ReserveResult(allowed=True, retry_after_sec=0)

    async def adjust(self, scopes: Sequence[Scope], delta: int) -> None:
        """İşlem bittiğinde gerçek token kullanımına göre bütçeyi düzeltir."""
        now = time.time()

        async with self._lock:
            for sc in scopes:
                # Süresi dolmuşsa temizle
                self._cleanup_expired(sc.key, now)

                if sc.key in self._data:
                    new_val = self._data[sc.key][0] + delta
                    # Dağıtık Sistem Kuralı: Bütçe sayacı asla eksiye düşemez (en az 0 olmalıdır)
                    self._data[sc.key][0] = max(0.0, new_val)
