"""İstek bazlı correlation ID bağlamı ve ASGI middleware modülü.

Bu modül, mikroservise gelen HTTP isteklerindeki 'X-Correlation-Id' başlığını yakalar,
güvenlik süzgecinden geçirir ve Python'un asenkron `ContextVar` yapısına kaydeder.
Böylece log formatter'lar, audit mekanizmaları veya Kafka producer'lar istek parametresi
taşımaya gerek kalmadan o anki aktif işlemin correlation ID'sine doğrudan erişebilir.
"""

from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.security import sanitize_correlation_id

# İstek boyunca o anki asenkron bağlamda aktif olan Correlation ID değerini tutar.
# İstek dışı durumlarda (arkaplan görevleri, açılış anı vb.) varsayılan olarak None döner.
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class RequestContextMiddleware:
    """X-Correlation-Id başlığını temizleyip ContextVar'a kaydeden saf ASGI middleware.

    MİMARİ UYARI:
    FastAPI / Starlette'in sunduğu `BaseHTTPMiddleware` burada BİLEREK KULLANILMAZ.
    BaseHTTPMiddleware, yanıt gövdesini (streaming response) ayrı bir arka plan task'inde
    işlettiği için ContextVar bağlamının alt görevlere kopyalanmasında ve geri dönüşünde
    bağlam kaybına (context loss) yol açar.
    Bu yüzden saf ASGI arayüzü (`__call__(scope, receive, send)`) kullanılmıştır.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Yalnızca HTTP isteklerini ele al (WebSocket, lifespan vb. kapsam dışıdır)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Gelen HTTP başlıkları arasında 'x-correlation-id' başlığını ara (küçük harfle)
        raw_header = next((v for k, v in scope["headers"] if k == b"x-correlation-id"), None)
        
        # Değer varsa latin-1 ile string'e çevir ve güvenlik süzgecinden geçir
        # CRLF (\r, \n) veya 64 karakterden uzun manipüle edilmiş değerler None olur.
        raw_str = raw_header.decode("latin-1") if raw_header else None
        sanitized = sanitize_correlation_id(raw_str)

        # Temizlenmiş değeri o anki ContextVar bağlamına kaydet ve sıfırlama anahtarını al
        token = correlation_id_var.set(sanitized)
        try:
            # İsteğin geri kalan middleware ve endpoint zincirini işlet
            await self.app(scope, receive, send)
        finally:
            # İstek sonlandığında (başarılı veya hatalı) bağlamı MUTLAKA temizle.
            # Bu işlem bellek sızıntısını ve sonraki isteklere ID sızmasını önler.
            correlation_id_var.reset(token)
