"""FastAPI lifespan runtime config başlatıcısı (_init_runtime_config) testleri."""

from unittest.mock import patch
import httpx
import pytest

from app.core.config import settings
from app.main import _init_runtime_config


@pytest.mark.anyio
async def test_init_runtime_config_disabled() -> None:
    """CONFIG_SERVER_ENABLED=False iken ağ çağrısı yapılmadığını ve holder'ın baseline ile hazırlandığını doğrular."""
    settings.CONFIG_SERVER_ENABLED = False
    holder, client = await _init_runtime_config()

    assert holder is not None
    assert client is None
    assert holder.status.source == "env"


@pytest.mark.anyio
async def test_init_runtime_config_fail_soft_when_server_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """CONFIG_SERVER_ENABLED=True ve sunucu kapalıyken CONFIG_FAIL_FAST=False ise servisin düşmediğini doğrular."""
    monkeypatch.setattr(settings, "CONFIG_SERVER_ENABLED", True)
    monkeypatch.setattr(settings, "CONFIG_FAIL_FAST", False)
    monkeypatch.setattr(settings, "CONFIG_INITIAL_ATTEMPTS", 1)

    # İletişim hatası fırlatan sahte transport
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Bağlantı reddedildi")

    with patch("app.main.ConfigServerClient") as mock_client_cls:
        from app.runtimeconfig.client import ConfigServerClient
        real_client = ConfigServerClient("http://localhost:8888/", transport=httpx.MockTransport(handler))
        mock_client_cls.return_value = real_client

        holder, client = await _init_runtime_config()

        assert holder is not None
        assert holder.status.source == "env"
        assert holder.status.consecutive_failures == 1
        await client.aclose()


@pytest.mark.anyio
async def test_init_runtime_config_fail_fast_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """CONFIG_FAIL_FAST=True iken Config Server'a ulaşılamazsa RuntimeError fırlatıldığını doğrular."""
    monkeypatch.setattr(settings, "CONFIG_SERVER_ENABLED", True)
    monkeypatch.setattr(settings, "CONFIG_FAIL_FAST", True)
    monkeypatch.setattr(settings, "CONFIG_INITIAL_ATTEMPTS", 1)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Bağlantı reddedildi")

    with patch("app.main.ConfigServerClient") as mock_client_cls:
        from app.runtimeconfig.client import ConfigServerClient
        real_client = ConfigServerClient("http://localhost:8888/", transport=httpx.MockTransport(handler))
        mock_client_cls.return_value = real_client

        with pytest.raises(RuntimeError, match="CONFIG_FAIL_FAST=true"):
            await _init_runtime_config()
