"""ConfigServerClient birim testleri.

httpx.MockTransport kullanılarak gerçek ağa çıkmadan tüm HTTP başarı ve hata
senaryoları (200 OK, 404/500 hataları, timeout, bozuk JSON) izole bir şekilde test edilir.
"""

import httpx
import pytest

from app.runtimeconfig.client import ConfigServerClient, ConfigServerError


@pytest.mark.anyio
async def test_client_fetch_success() -> None:
    """Başarılı 200 OK cevabında propertySources listesinin doğru döndüğünü doğrular."""
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "name": "ai-assistant-service",
                "profiles": ["dev"],
                "propertySources": [
                    {"name": "ai-assistant-service.yaml", "source": {"ai.agent.max-steps": 4}}
                ],
            },
        )

    # base_url sonu '/' olmadan verilse dahi doğru URL oluşturulmalı
    transport = httpx.MockTransport(handler)
    client = ConfigServerClient("http://config-server:8888", timeout_sec=2.0, transport=transport)

    sources = await client.fetch_property_sources("ai-assistant-service", "dev")
    await client.aclose()

    assert len(sources) == 1
    assert sources[0]["source"]["ai.agent.max-steps"] == 4

    # İsteğin doğru URL ve Accept başlığı ile gittiğini doğrula
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.url == "http://config-server:8888/ai-assistant-service/dev"
    assert req.headers["Accept"] == "application/json"


@pytest.mark.anyio
async def test_client_http_error_status_codes() -> None:
    """404 veya 500 gibi HTTP durum kodlarında ConfigServerError fırlatıldığını doğrular."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client = ConfigServerClient("http://localhost:8888/", transport=httpx.MockTransport(handler))
    with pytest.raises(ConfigServerError, match="HTTP 404"):
        await client.fetch_property_sources("ai-assistant-service", "dev")
    await client.aclose()


@pytest.mark.anyio
async def test_client_timeout_error() -> None:
    """Ağ zaman aşımı (ReadTimeout) durumunda ConfigServerError fırlatıldığını ve URL sızmadığını doğrular."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Sunucu yanıt vermedi")

    client = ConfigServerClient("http://localhost:8888/", transport=httpx.MockTransport(handler))
    with pytest.raises(ConfigServerError) as exc_info:
        await client.fetch_property_sources("ai-assistant-service", "dev")
    await client.aclose()

    # Hata mesajında exception adı geçmeli ancak URL geçmemelidir
    assert "ReadTimeout" in str(exc_info.value)
    assert "http://" not in str(exc_info.value)


@pytest.mark.anyio
async def test_client_malformed_json_or_missing_property_sources() -> None:
    """Geçersiz JSON veya 'propertySources' içermeyen yanıtlarda ConfigServerError fırlatıldığını doğrular."""
    # 1. Bozuk JSON
    client_bad_json = ConfigServerClient(
        "http://localhost:8888/",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text="<not-json>")),
    )
    with pytest.raises(ConfigServerError, match="geçerli bir JSON"):
        await client_bad_json.fetch_property_sources("ai-assistant-service", "dev")
    await client_bad_json.aclose()

    # 2. propertySources alanı yok
    client_missing = ConfigServerClient(
        "http://localhost:8888/",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"name": "test"})),
    )
    with pytest.raises(ConfigServerError, match="propertySources"):
        await client_missing.fetch_property_sources("ai-assistant-service", "dev")
    await client_missing.aclose()

    # 3. propertySources liste değil
    client_not_list = ConfigServerClient(
        "http://localhost:8888/",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"propertySources": "invalid"})),
    )
    with pytest.raises(ConfigServerError, match="liste tipinde"):
        await client_not_list.fetch_property_sources("ai-assistant-service", "dev")
    await client_not_list.aclose()
