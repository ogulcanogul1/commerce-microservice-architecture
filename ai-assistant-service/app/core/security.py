"""Güvenlik bağımlılıkları ve istek bağlamı (Security Dependencies & RequestContext).

Bu modül iki temel savunma mekanizmasını yönetir:
1. Çevre Güvenliği (Perimeter Security / Gateway Bypass Koruması):
   Mikroservise doğrudan gelen yetkisiz çağrıları engellemek için API Gateway tarafından
   eklenen 'X-Gateway-Secret' gizli başlığını doğrular (`require_gateway_secret`).
2. Kimlik Çıkarımı ve Doğrulama (Identity Extraction & Normalization):
   API Gateway'in JWT'den çözerek eklediği 'X-User-Id' başlığını alır, doğrular, normalize eder
   ve tüm iş katmanında değiştirilemez şekilde taşınacak `RequestContext` nesnesini oluşturur.
"""

from dataclasses import dataclass
import hmac
import re
import uuid

from fastapi import Header, HTTPException, status

from app.core.audit import write_audit
from app.core.config import settings

# Correlation ID Doğrulama Deseni:
# API Gateway genelde UUID üretir; yalnızca alfanümerik karakterlere (A-Z, a-z, 0-9),
# noktaya (.), alt çizgiye (_) ve tireye (-) izin verilir. Maksimum 64 karakterle sınırlandırılır.
# Bu katı kural sayesinde 'Log Enjeksiyonu' (CRLF / \r\n saldırıları) ve bellek şişirme engellenir.
_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


def _sanitize_correlation_id(value: str | None) -> str | None:
    """Gelen X-Correlation-Id başlığını temizler ve doğrular.

    - Değer None ise doğrudan None döner.
    - Başındaki ve sonundaki boşlukları temizler (.strip()).
    - Regex desenine tam uyuyorsa temiz halini döner, uymuyorsa None döner.
    - GÜVENLİK NOTU: Geçersiz metin asla hata mesajına veya loga yazılmaz (enjeksiyonu önlemek için).
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped if _CORRELATION_ID_PATTERN.fullmatch(stripped) else None


@dataclass(frozen=True)
class RequestContext:
    """Her HTTP isteği boyunca taşınan değiştirilemez (immutable / frozen) kimlik ve izleme bağlamı.

    - user_id: Gateway tarafından onaylanmış, standart küçük harfli UUID (Örn: '123e4567-e89b-12d3-a456-426614174000').
    - correlation_id: Temizlenmiş ve güvenli hale getirilmiş dağıtık izleme kimliği (opsiyonel).
    """

    user_id: str
    correlation_id: str | None


async def get_request_context(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-Id"),
) -> RequestContext:
    """İstemci kimliğini Gateway'in enjekte ettiği X-User-Id başlığından çıkarır ve doğrular.

    Güvenlik Kontrolleri:
    1. Header tamamen eksikse veya boşsa: 401 Unauthorized fırlatır ve 'missing_identity' audit kaydı düşer.
    2. Header geçerli bir UUID formatında değilse (örn. SQL enjeksiyon denemesi veya düz metin):
       401 Unauthorized fırlatır ve 'invalid_identity' audit kaydı düşer.
    3. Geçerli ise UUID küçük harfe normalize edilir ve RequestContext olarak döndürülür.
    """
    # 1. Başlık eksik veya boşluklardan mı ibaret?
    if not x_user_id or not x_user_id.strip():
        write_audit("perimeter_denied", user_id=None, correlation_id=None, outcome="missing_identity")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kimlik doğrulanamadı.",
        )

    # 2. Değer geçerli bir RFC 4122 UUID'si mi?
    try:
        parsed_uuid = uuid.UUID(x_user_id.strip())
    except (ValueError, AttributeError):
        write_audit("perimeter_denied", user_id=None, correlation_id=None, outcome="invalid_identity")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kimlik doğrulanamadı.",
        )

    # 3. Standardize edilmiş küçük harfli UUID ile RequestContext nesnesi oluştur
    normalized_user_id = str(parsed_uuid).lower()
    return RequestContext(
        user_id=normalized_user_id,
        correlation_id=_sanitize_correlation_id(x_correlation_id),
    )


async def require_gateway_secret(
    x_gateway_secret: str | None = Header(None, alias="X-Gateway-Secret"),
) -> None:
    """Gateway Bypass Koruması (Doğrudan Servis Çağrısını Engelleme).

    İstemcilerin veya saldırganların API Gateway'i atlayarak (bypass) mikroservise doğrudan HTTP isteği
    atmasını engellemek için yalnızca Gateway'in bildiği 'X-Gateway-Secret' başlığını zorunlu kılar.

    Güvenlik Detayları:
    - Sabit Zamanlı Karşılaştırma (Constant-Time): 'hmac.compare_digest' kullanılır. Klasik '==' veya 'equals'
      işlemi ilk farklı karakterde döndüğü için saldırganlar milisaniyelik gecikme farklarından (Timing Attack)
      secret token'ı karakter karakter tahmin edebilir. 'compare_digest' her durumda eşit sürede tamamlanır.
    - Hata Yanıtı Hijyeni: 403 Forbidden yanıtı dönerken beklenen secret token asla mesajda ifşa edilmez.
    """
    # Geliştirme/test ortamında bayrak kapalıysa kontrolü atla
    if not settings.GATEWAY_SECURITY_ENABLED:
        return

    expected_secret = settings.GATEWAY_INTERNAL_SECRET
    # Sabit zamanlı güvenli karşılaştırma ile secret doğrulaması
    if not x_gateway_secret or not hmac.compare_digest(x_gateway_secret, expected_secret):
        write_audit("perimeter_denied", user_id=None, correlation_id=None, outcome="secret_mismatch")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doğrudan erişim engellendi.",
        )
