"""EurekaRegistrar, graceful drain ve host çözümleme birim testleri."""

import asyncio
from collections.abc import AsyncIterator
import signal
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.discovery.client import EurekaClient, EurekaError
from app.discovery.drain import install_sigterm_drain
from app.discovery.models import InstanceInfo
from app.discovery.network import resolve_instance_host
from app.discovery.registrar import EurekaRegistrar


class FakeEurekaClient:
    """Ağ çağrısı yapmayan, çağrı sayılarını ve durumları kaydeden test istemcisi."""

    def __init__(self) -> None:
        self.register_calls = 0
        self.heartbeat_calls = 0
        self.set_status_calls: list[str] = []
        self.deregister_calls = 0
        self.closed = False

        self.heartbeat_return_values: list[bool] = []
        self.register_error: Exception | None = None
        self.heartbeat_error: Exception | None = None
        self.set_status_error: Exception | None = None
        self.deregister_error: Exception | None = None

    async def register(self, info: InstanceInfo) -> None:
        self.register_calls += 1
        if self.register_error:
            raise self.register_error

    async def heartbeat(self, info: InstanceInfo) -> bool:
        self.heartbeat_calls += 1
        if self.heartbeat_error:
            err = self.heartbeat_error
            self.heartbeat_error = None  # Tek seferlik fırlat
            raise err
        if self.heartbeat_return_values:
            return self.heartbeat_return_values.pop(0)
        return True

    async def set_status(self, info: InstanceInfo, status: str) -> None:
        self.set_status_calls.append(status)
        if self.set_status_error:
            raise self.set_status_error

    async def deregister(self, info: InstanceInfo) -> None:
        self.deregister_calls += 1
        if self.deregister_error:
            raise self.deregister_error

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def dummy_instance_info() -> InstanceInfo:
    return InstanceInfo(
        app_name="AI-ASSISTANT-SERVICE",
        instance_id="127.0.0.1:ai-assistant-service:8089",
        host="127.0.0.1",
        ip_addr="127.0.0.1",
        port=8089,
        health_url="http://127.0.0.1:8089/health",
        renewal_sec=10,
        lease_sec=30,
    )


@pytest.mark.anyio
async def test_registrar_start_calls_register_and_starts_heartbeat(
    dummy_instance_info: InstanceInfo,
) -> None:
    client = FakeEurekaClient()
    registrar = EurekaRegistrar(
        client=client,  # type: ignore[arg-type]
        info=dummy_instance_info,
        renewal_sec=0.05,
        drain_sec=1,
    )

    await registrar.start()
    assert client.register_calls == 1

    # Heartbeat görevinin çalıştığını gözlemlemek için kısa süre bekle
    await asyncio.sleep(0.12)
    assert client.heartbeat_calls >= 2

    await registrar.stop()
    assert client.closed is True


@pytest.mark.anyio
async def test_registrar_re_registers_when_heartbeat_returns_404(
    dummy_instance_info: InstanceInfo,
) -> None:
    client = FakeEurekaClient()
    # İlk heartbeat 404 (False) dönsün, ikincisi 200 (True)
    client.heartbeat_return_values = [False, True]

    registrar = EurekaRegistrar(
        client=client,  # type: ignore[arg-type]
        info=dummy_instance_info,
        renewal_sec=0.05,
    )

    await registrar.start()
    assert client.register_calls == 1  # İlk start kaydı

    await asyncio.sleep(0.08)
    # 404 döndüğü için registrar tekrar register çağırmış olmalı
    assert client.register_calls >= 2

    await registrar.stop()


@pytest.mark.anyio
async def test_registrar_survives_heartbeat_eureka_error(
    dummy_instance_info: InstanceInfo,
) -> None:
    client = FakeEurekaClient()
    client.heartbeat_error = EurekaError("Geçici ağ hatası")

    registrar = EurekaRegistrar(
        client=client,  # type: ignore[arg-type]
        info=dummy_instance_info,
        renewal_sec=0.05,
    )

    await registrar.start()
    await asyncio.sleep(0.12)

    # Hata olmasına rağmen döngü ölmedi, sonraki nabzı denedi
    assert client.heartbeat_calls >= 2

    await registrar.stop()


@pytest.mark.anyio
async def test_registrar_start_resilient_to_initial_register_failure(
    dummy_instance_info: InstanceInfo,
) -> None:
    client = FakeEurekaClient()
    client.register_error = EurekaError("Eureka henüz ayakta değil")

    registrar = EurekaRegistrar(
        client=client,  # type: ignore[arg-type]
        info=dummy_instance_info,
        renewal_sec=0.05,
    )

    # start hata fırlatmamalı (fail-open)
    await registrar.start()
    assert client.register_calls == 1

    # Sonraki turlarda heartbeat çalışmaya devam edebilmeli
    await asyncio.sleep(0.08)
    assert client.heartbeat_calls >= 1

    await registrar.stop()


@pytest.mark.anyio
async def test_drain_and_deregister_sequence_and_idempotency(
    dummy_instance_info: InstanceInfo,
) -> None:
    client = FakeEurekaClient()
    registrar = EurekaRegistrar(
        client=client,  # type: ignore[arg-type]
        info=dummy_instance_info,
        renewal_sec=10,
    )

    await registrar.start()
    await registrar.drain_and_deregister()

    assert client.set_status_calls == ["OUT_OF_SERVICE"]
    assert client.deregister_calls == 1

    # İkinci çağrı no-op olmalı (idempotent)
    await registrar.drain_and_deregister()
    assert client.set_status_calls == ["OUT_OF_SERVICE"]
    assert client.deregister_calls == 1

    await registrar.stop()


@pytest.mark.anyio
async def test_drain_and_deregister_continues_even_if_set_status_fails(
    dummy_instance_info: InstanceInfo,
) -> None:
    client = FakeEurekaClient()
    client.set_status_error = EurekaError("Status güncellenemedi")

    registrar = EurekaRegistrar(
        client=client,  # type: ignore[arg-type]
        info=dummy_instance_info,
        renewal_sec=10,
    )

    await registrar.start()
    await registrar.drain_and_deregister()

    # set_status hata verse bile deregister çağrılmalıdır
    assert client.deregister_calls == 1

    await registrar.stop()


def test_resolve_instance_host_with_configured_host() -> None:
    # 1. Configured host verildiğinde ve prefer_ip=True
    host, ip = resolve_instance_host("127.0.0.1", prefer_ip=True)
    assert host == "127.0.0.1"
    assert ip == "127.0.0.1"

    # 2. Configured host DNS adı olduğunda ve prefer_ip=False
    host, ip = resolve_instance_host("localhost", prefer_ip=False)
    assert host == "localhost"
    assert ip in ("127.0.0.1", "::1")


def test_resolve_instance_host_default_detection() -> None:
    # Parametre verilmediğinde makine IP'sini otomatik çözer
    host, ip = resolve_instance_host("", prefer_ip=True)
    assert host == ip
    assert len(ip) > 0


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM drain testi POSIX ortamlar içindir")
def test_install_sigterm_drain_posix(dummy_instance_info: InstanceInfo) -> None:
    client = FakeEurekaClient()
    registrar = EurekaRegistrar(
        client=client,  # type: ignore[arg-type]
        info=dummy_instance_info,
    )

    mock_previous = MagicMock()
    with patch("signal.getsignal", return_value=mock_previous), patch("signal.signal") as mock_signal:
        restore = install_sigterm_drain(registrar, drain_sec=0)
        assert callable(restore)
        assert mock_signal.called


def test_install_sigterm_drain_windows_noop(dummy_instance_info: InstanceInfo) -> None:
    client = FakeEurekaClient()
    registrar = EurekaRegistrar(
        client=client,  # type: ignore[arg-type]
        info=dummy_instance_info,
    )

    with patch("sys.platform", "win32"):
        restore = install_sigterm_drain(registrar, drain_sec=10)
        assert callable(restore)
        # Windows'ta no-op lambda döner ve hata fırlatmaz
        restore()


@pytest.mark.anyio
async def test_lifespan_eureka_disabled_by_default() -> None:
    """EUREKA_ENABLED=False iken lifespan içinde eureka_registrar None olmalı ve ağ çağrısı yapılmamalı."""
    from app.main import app, lifespan

    async with lifespan(app):
        assert app.state.eureka_registrar is None
