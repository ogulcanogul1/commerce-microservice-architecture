"""Spring Cloud Config Server REST İstemcisi (ConfigServerClient).

Bu modül, Spring Cloud Config Server'ın REST uç noktası olan:
    GET /{app_name}/{profile}
ile asenkron HTTP üzerinden haberleşir ve dönen konfigürasyon kaynaklarını
(propertySources) çeker.

Mimari ve Tasarım Prensipleri:
1. Tek Sorumluluk İlkesi (SRP):
   Bu istemci yalnızca HTTP GET çağrısını yönetir, JSON yanıtını doğrular ve
   'propertySources' listesini döner. Yeniden deneme (retry) döngüsü veya periyodik
   sorgulama (polling) bu sınıfa ait değildir (Adım 5'te ConfigPoller tarafından yapılır).
2. Güvenlik İlkesi (Security Guideline):
   Hata ve log mesajlarına tam URL veya query parametreleri ASLA yazılmaz. Yalnızca
   HTTP durum kodu veya hata türü (örn: Timeout, HTTP 404) belirtilir.
3. Test Edilebilirlik (Testability):
   'transport' parametresi enjekte edilebilir; bu sayede birim testlerinde gerçek ağa
   çıkmadan httpx.MockTransport ile sahte yanıtlar üretilebilir.
"""

from typing import Any
import httpx


class ConfigServerError(Exception):
    """Config Server REST API ile iletişim sırasında oluşan ağ ve durum hataları için özel istisna sınıfı.

    Güvenlik İlkesi:
    Hata mesajları içerisine hassas URL parametreleri veya ortam bilgileri YAZILMAZ.
    Sadece HTTP durum kodu ve operasyonel hata nedeni belirtilir.
    """

    pass


class ConfigServerClient:
    """Spring Cloud Config Server ile asenkron HTTP üzerinden haberleşen REST istemcisi."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_sec: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Config Server istemcisini başlatır.

        Args:
            base_url: Config Server temel erişim adresi (örn: 'http://localhost:8888/').
            timeout_sec: Tekil REST GET çağrısı zaman aşımı süresi (saniye cinsinden, varsayılan: 3.0s).
                         Config Server yanıt vermediğinde servisin kilitlenmemesi için kısa tutulur.
            transport: Birim testlerinde sahte yanıt (MockTransport) enjekte edebilmek için transport nesnesi.
        """
        # Config Server URL'inin sonunda her zaman '/' eğik çizgi olmasını garanti ediyoruz
        # httpx.AsyncClient(base_url=...) göreli yolları birleştirirken son '/' karakterine ihtiyaç duyar
        normalized_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self._base_url = normalized_url

        # Tek bir oturum (connection pooling) üzerinden asenkron HTTP istemcisi oluşturulur
        # JSON yanıt almak istediğimizi 'Accept: application/json' başlığıyla belirtiyoruz
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout_sec,
            headers={"Accept": "application/json"},
            transport=transport,
        )

    async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
        """Config Server'dan ilgili servis ve profile ait propertySources listesini çeker.

        Spring Cloud Config REST Protokolü:
            GET /{app_name}/{profile}
            Örnek: GET /ai-assistant-service/dev
            Başarılı Yanıt: 200 OK + JSON { "name": "...", "propertySources": [ ... ] }

        Args:
            app_name: Servis adı (örn: 'ai-assistant-service').
            profile: Konfigürasyon profili (örn: 'dev', 'qa', 'prod').

        Returns:
            Config Server'dan dönen sıralı 'propertySources' listesi.
            Her eleman {"name": "...", "source": { ... }} yapısındadır.

        Raises:
            ConfigServerError: Ağ hatası, HTTP 200 dışı yanıt, geçersiz JSON veya eksik 'propertySources'.
        """
        clean_app = app_name.strip("/")
        clean_profile = profile.strip("/")
        path = f"{clean_app}/{clean_profile}"

        # 1. Aşama: HTTP İsteğini Gönderme ve Ağ Hatalarını Yakalama
        try:
            response = await self._client.get(path)
        except httpx.HTTPError as exc:
            # URL sızdırmadan sadece hata sınıfının adını ve sebebini sarıyoruz
            raise ConfigServerError(
                f"Config Server HTTP bağlantı hatası: {type(exc).__name__}"
            ) from exc

        # 2. Aşama: HTTP Durum Kodu Kontrolü (Sadece 200 OK kabul edilir)
        if response.status_code != 200:
            raise ConfigServerError(
                f"Config Server GET başarısız: HTTP {response.status_code}"
            )

        # 3. Aşama: JSON Ayrıştırma
        try:
            data = response.json()
        except ValueError as exc:
            raise ConfigServerError("Config Server cevabı geçerli bir JSON formatında değil") from exc

        # 4. Aşama: Şema Doğrulama (Spring Cloud Config 'propertySources' alanı içermelidir)
        if not isinstance(data, dict) or "propertySources" not in data:
            raise ConfigServerError(
                "Config Server cevabında 'propertySources' alanı bulunamadı"
            )

        sources = data["propertySources"]
        if not isinstance(sources, list):
            raise ConfigServerError(
                "Config Server 'propertySources' alanı liste tipinde olmalıdır"
            )

        return sources

    async def aclose(self) -> None:
        """HTTP istemci soketlerini ve bağlantı havuzunu güvenle kapatır."""
        await self._client.aclose()
