import httpx

from app.discovery.models import InstanceInfo, InstanceStatus


class EurekaError(Exception):
    """Eureka REST API ile iletişim sırasında oluşan ağ ve durum hataları için özel istisna sınıfı.

    Güvenlik İlkesi (Security Guideline):
    Hata mesajları içerisine hassas URL parametreleri veya istek gövdeleri (payload) YAZILMAZ.
    Sadece HTTP durum kodu ve operasyon adı belirtilir.
    """

    pass


class EurekaClient:
    """Eureka REST API (v2) ile asenkron HTTP üzerinden haberleşen istemci sınıfı.

    Bu sınıf sadece temel REST işlemlerini (kayıt, nabız, durum güncelleme, silme) yürütür.
    Arka plan döngüsü ve yeniden deneme mantığı bir sonraki katman olan `EurekaRegistrar`'a aittir.
    """

    def __init__(
        self,
        base_url: str,
        timeout_sec: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Eureka istemcisini başlatır.

        Args:
            base_url: Eureka sunucu kök adresi (örn: 'http://localhost:8761/eureka/').
            timeout_sec: REST çağrılarında zaman aşımı (Eureka yanıt vermiyorsa servisi kitlememesi için kısa tutulur: 3.0s).
            transport: Birim testlerinde ağa çıkmadan sahte yanıt (MockTransport) verebilmek için enjekte edilebilir transport.
        """
        # Eureka URL'inin sonunda her zaman '/' olduğundan emin oluyoruz (httpx path birleştirmesi için zorunlu)
        normalized_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self._base_url = normalized_url

        # Tek bir oturum (connection pooling) üzerinden haberleşen asenkron HTTP istemcisi
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout_sec,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    async def register(self, info: InstanceInfo) -> None:
        """Mikroservis instance'ını Eureka sunucusuna ilk kez kaydeder.

        HTTP Protokolü:
            POST /eureka/apps/{APP_NAME}
            Body: InstanceInfo JSON
            Başarılı Yanıt: 204 No Content (veya bazı versiyonlarda 200 OK)
        """
        url = f"apps/{info.app_name}"
        try:
            response = await self._client.post(url, json=info.to_payload())
            # Eureka kayıt başarılı olduğunda 204 No Content döner
            if response.status_code not in (200, 204):
                raise EurekaError(
                    f"Eureka kaydı başarısız oldu, HTTP durum kodu: {response.status_code}"
                )
        except httpx.HTTPError as exc:
            # Ağ hatasını (bağlantı reddi, DNS arızası vb.) EurekaError'a sararak dışarı sızdırmıyoruz
            raise EurekaError(f"Eureka kayıt ağ hatası: {type(exc).__name__}") from exc

    async def heartbeat(self, info: InstanceInfo) -> bool:
        """Eureka sunucusuna 'ben hâlâ sağlıklıyım ve ayaktayım' nabzı gönderir.

        HTTP Protokolü:
            PUT /eureka/apps/{APP_NAME}/{instance_id}?status=UP
            Başarılı Yanıt: 200 OK

        Kritik Dağıtık Sistem Mantığı:
            - Eğer Eureka sunucusu restart edilmişse ya da ağ kesintisi yüzünden servisin
              süresi (lease) dolup listeden silinmişse, Eureka bu isteğe 404 Not Found döner.
            - Bu durumda istemci hata fırlatmaz; 'False' döndürür!
            - Çağıran katman (Registrar), False cevabını alınca servisi hemen yeniden kaydeder (re-register).

        Returns:
            True: Nabız kabul edildi (200 OK).
            False: Kayıt Eureka'da bulunamadı (404 Not Found), yeniden kaydolunmalı.
        """
        url = f"apps/{info.app_name}/{info.instance_id}"
        try:
            response = await self._client.put(url, params={"status": "UP"})
            if response.status_code == 200:
                return True
            if response.status_code == 404:
                # 404 bir arıza değil, 'kaydın düştüğü' ve tekrar register olunması gerektiği sinyalidir
                return False
            raise EurekaError(
                f"Eureka heartbeat başarısız oldu, HTTP durum kodu: {response.status_code}"
            )
        except httpx.HTTPError as exc:
            raise EurekaError(f"Eureka heartbeat ağ hatası: {type(exc).__name__}") from exc

    async def set_status(self, info: InstanceInfo, status: InstanceStatus | str) -> None:
        """Servisin Eureka'daki durumunu günceller (Örn: InstanceStatus.OUT_OF_SERVICE).

        Neden kullanılır? (Graceful Shutdown):
            Uygulama kapatılmadan önce (SIGTERM sinyalinde) durum 'OUT_OF_SERVICE' yapılır.
            Böylece Gateway ve diğer servisler bu instance'a yeni trafik yönlendirmeyi durdurur.

        HTTP Protokolü:
            PUT /eureka/apps/{APP_NAME}/{instance_id}/status?value={status}
            Başarılı Yanıt: 200 OK
        """
        status_value = str(status.value if isinstance(status, InstanceStatus) else status)
        url = f"apps/{info.app_name}/{info.instance_id}/status"
        try:
            response = await self._client.put(url, params={"value": status_value})
            if response.status_code != 200:
                raise EurekaError(
                    f"Eureka durum güncellemesi başarısız oldu, HTTP durum kodu: {response.status_code}"
                )
        except httpx.HTTPError as exc:
            raise EurekaError(f"Eureka durum güncelleme ağ hatası: {type(exc).__name__}") from exc

    async def deregister(self, info: InstanceInfo) -> None:
        """Servis kapanırken Eureka'daki kaydını tamamen siler.

        HTTP Protokolü:
            DELETE /eureka/apps/{APP_NAME}/{instance_id}
            Başarılı Yanıt: 200 OK

        İdempotentlik (Idempotence):
            Eğer servis zaten silinmişse Eureka 404 Not Found döner. Kapanış sırasında
            bu durum bir hata sayılmaz; sessizce başarılı kabul edilir.
        """
        url = f"apps/{info.app_name}/{info.instance_id}"
        try:
            response = await self._client.delete(url)
            if response.status_code not in (200, 204, 404):
                raise EurekaError(
                    f"Eureka kaydı silinemedi, HTTP durum kodu: {response.status_code}"
                )
        except httpx.HTTPError as exc:
            raise EurekaError(f"Eureka silme ağ hatası: {type(exc).__name__}") from exc

    async def aclose(self) -> None:
        """Arka plandaki HTTP istemcisini ve açık bağlantı havuzunu (connection pool) zarifçe kapatır."""
        await self._client.aclose()
