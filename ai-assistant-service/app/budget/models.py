"""Token bütçesi veri modelleri.

Mimari Kural:
Tüm bütçe modelleri immutable (değiştirilemez - frozen=True) dataclass olarak tanımlanır.
Bu sayede rezervasyon verileri süreç içinde yanlışlıkla mutasyona uğramaz ve thread/async güvenlidir.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    """Belirli bir zaman dilimi veya sağlayıcı için tek bir token sayacını tanımlar.
    
    Örnekler:
    - Günlük kullanıcı kotası: key='tok:user:123:day:20261108', limit=50000, ttl_sec=172800
    - Dakikalık kullanıcı kotası: key='tok:user:123:min:29900000', limit=8000, ttl_sec=120
    - Tüm servisin ortak TPM kotası: key='tok:provider:gemini:min:29900000', limit=100000, ttl_sec=120
    """

    # Redis veya bellek içindeki tekil sayaç anahtarı (Key)
    key: str

    # Bu sayaç için izin verilen maksimum token miktarı (Üst sınır)
    limit: int

    # Sayacın geçerlilik süresi (Time-To-Live - saniye cinsinden)
    # Süresi dolan anahtar otomatik olarak silinir veya sıfırlanır
    ttl_sec: int


@dataclass(frozen=True)
class ReserveResult:
    """Token rezervasyon denemesinin sonucunu taşır.
    
    Kullanıcı LLM'e gitmeden önce bu sonuca bakılır:
    - allowed True ise: İstek işleme alınır.
    - allowed False ise: 429 TokenBudgetExceeded fırlatılır.
    """

    # Bütçe yeterli mi? (True: kota var ve token rezerve edildi, False: kota doldu)
    allowed: bool

    # Kota aşıldıysa (allowed=False), bu sayacın sıfırlanmasına kalan saniye süresi.
    # HTTP 'Retry-After' başlığına doğrudan bu değer yazılır.
    retry_after_sec: int

    # Hangi sayacın limiti aştığını belirten anahtar (İç sunucu loglarında analiz için tutulur, dışarı sızdırılmaz)
    exceeded_key: str | None = None
