"""EurekaClient Birim Testleri.

Bu testler sıfır ağ bağımlılığı ile (Docker veya gerçek Eureka olmadan) çalışır.
`httpx.MockTransport` kullanarak sanal bir Eureka HTTP sunucusu simüle ederiz.
Bu sayede testler milisaniyeler içinde tamamlanır ve deterministiktir.
"""

import json
import httpx
import pytest

from app.discovery.client import EurekaClient, EurekaError
from app.discovery.models import InstanceInfo, InstanceStatus


@pytest.fixture
def sample_info() -> InstanceInfo:
    """Testlerde kullanılacak örnek mikroservis instance bilgisi fixture'ı."""
    return InstanceInfo(
        app_name="AI-ASSISTANT-SERVICE",
        instance_id="192.168.1.100:ai-assistant-service:8089",
        host="192.168.1.100",
        ip_addr="192.168.1.100",
        port=8089,
        health_url="http://192.168.1.100:8089/health",
        renewal_sec=10,
        lease_sec=30,
    )


def test_instance_info_payload_structure(sample_info: InstanceInfo) -> None:
    """Eureka'ya gönderilecek JSON payload formatının spesifikasyona tam uyduğunu doğrular."""
    payload = sample_info.to_payload()
    instance = payload["instance"]

    # 1. Uygulama adı büyük harf olmalı (Eureka standardı)
    assert instance["app"] == "AI-ASSISTANT-SERVICE"

    # 2. Instance ID tekil olmalı
    assert instance["instanceId"] == sample_info.instance_id

    # 3. Gateway LoadBalancer'ın kullandığı vipAddress küçük harf olmalı
    assert instance["vipAddress"] == "ai-assistant-service"

    # 4. İlk kayıt durumu 'UP' (çalışıyor) olmalı
    assert instance["status"] == "UP"

    # 5. Port bilgisi XML/JSON yapısına uygun olarak `$` anahtarıyla gelmeli
    assert instance["port"]["$"] == 8089

    # 6. Lease (kiralama) ve yenileme süreleri doğru ayarlanmış olmalı
    assert instance["leaseInfo"]["renewalIntervalInSecs"] == 10
    assert instance["leaseInfo"]["durationInSecs"] == 30


@pytest.mark.anyio
async def test_register_success(sample_info: InstanceInfo) -> None:
    """Eureka kaydının (POST /apps/...) 204 No Content ile başarılı olduğunu doğrular."""

    # Sahte HTTP sunucu işleyicisi: gelen isteği denetler
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/eureka/apps/AI-ASSISTANT-SERVICE"
        data = json.loads(request.content)
        assert data["instance"]["app"] == "AI-ASSISTANT-SERVICE"
        # Eureka başarılı kayıtta 204 No Content döner
        return httpx.Response(204)

    client = EurekaClient(
        base_url="http://localhost:8761/eureka/",
        transport=httpx.MockTransport(handler),
    )
    # Hata fırlatmadan tamamlanmalıdır
    await client.register(sample_info)
    await client.aclose()


@pytest.mark.anyio
async def test_register_failure_raises_eureka_error(sample_info: InstanceInfo) -> None:
    """Eureka sunucusu 500 İç Sunucu Hatası dönerse EurekaError fırlatıldığını doğrular."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = EurekaClient(
        base_url="http://localhost:8761/eureka/",
        transport=httpx.MockTransport(handler),
    )
    # 500 durumunda EurekaError fırlatılmalı ve hata mesajında durum kodu yer almalı
    with pytest.raises(EurekaError, match="HTTP durum kodu: 500"):
        await client.register(sample_info)
    await client.aclose()


@pytest.mark.anyio
async def test_heartbeat_returns_true_on_200(sample_info: InstanceInfo) -> None:
    """Heartbeat başarılı (200 OK) olduğunda metodun True döndüğünü doğrular."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert sample_info.instance_id in request.url.path
        assert request.url.params["status"] == "UP"
        return httpx.Response(200)

    client = EurekaClient(
        base_url="http://localhost:8761/eureka/",
        transport=httpx.MockTransport(handler),
    )
    assert await client.heartbeat(sample_info) is True
    await client.aclose()


@pytest.mark.anyio
async def test_heartbeat_returns_false_on_404(sample_info: InstanceInfo) -> None:
    """Eureka servisi unuttuğunda (404 Not Found), yeniden kayıt sinyali olarak False döndüğünü doğrular."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = EurekaClient(
        base_url="http://localhost:8761/eureka/",
        transport=httpx.MockTransport(handler),
    )
    # 404 hata fırlatmaz, yeniden kayıt için False döner!
    assert await client.heartbeat(sample_info) is False
    await client.aclose()


@pytest.mark.anyio
async def test_heartbeat_raises_eureka_error_on_500(sample_info: InstanceInfo) -> None:
    """Heartbeat sırasında beklenmeyen bir 500 hatası alındığında EurekaError fırlatıldığını doğrular."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = EurekaClient(
        base_url="http://localhost:8761/eureka/",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EurekaError):
        await client.heartbeat(sample_info)
    await client.aclose()


@pytest.mark.anyio
async def test_set_status_success(sample_info: InstanceInfo) -> None:
    """Servis durumunun (Örn: OUT_OF_SERVICE) başarıyla güncellendiğini doğrular."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.params["value"] == "OUT_OF_SERVICE"
        return httpx.Response(200)

    client = EurekaClient(
        base_url="http://localhost:8761/eureka/",
        transport=httpx.MockTransport(handler),
    )
    await client.set_status(sample_info, InstanceStatus.OUT_OF_SERVICE)
    await client.aclose()


@pytest.mark.anyio
async def test_deregister_success_and_404_ignored(sample_info: InstanceInfo) -> None:
    """Kaydı silerken hem 200 hem de 404 (zaten silinmiş) durumlarının güvenle kabul edildiğini doğrular."""

    def handler_200(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(200)

    def handler_404(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(404)

    # 1. Durum: Normal silme (200 OK)
    client_200 = EurekaClient("http://localhost:8761/eureka/", transport=httpx.MockTransport(handler_200))
    await client_200.deregister(sample_info)
    await client_200.aclose()

    # 2. Durum: İdempotent silme (zaten yoksa 404 gelse bile hata vermez)
    client_404 = EurekaClient("http://localhost:8761/eureka/", transport=httpx.MockTransport(handler_404))
    await client_404.deregister(sample_info)
    await client_404.aclose()


@pytest.mark.anyio
async def test_timeout_raises_eureka_error_without_sensitive_info(sample_info: InstanceInfo) -> None:
    """Zaman aşımında (Timeout) EurekaError fırlatıldığını ve loglarda URL/token sızmadığını doğrular."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Bağlantı zaman aşımına uğradı")

    client = EurekaClient(
        base_url="http://localhost:8761/eureka/",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EurekaError) as exc_info:
        await client.register(sample_info)

    # Güvenlik Kontrolü: Hata mesajı asla URL veya endpoint sızdırmamalıdır
    error_message = str(exc_info.value)
    assert "http://" not in error_message
    assert "localhost" not in error_message
    assert "Eureka kayıt ağ hatası: ReadTimeout" in error_message

    await client.aclose()
