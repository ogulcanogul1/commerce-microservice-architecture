"""initial_load fonksiyonu birim testleri."""

from typing import Any
import pytest

from app.core.config import Settings
from app.runtimeconfig.client import ConfigServerClient, ConfigServerError
from app.runtimeconfig.holder import RuntimeConfigHolder
from app.runtimeconfig.loader import initial_load
from app.runtimeconfig.models import RuntimeSettings


@pytest.fixture
def baseline_holder() -> RuntimeConfigHolder:
    baseline = RuntimeSettings.from_startup(Settings(_env_file=None))
    return RuntimeConfigHolder(baseline, frozenset())


@pytest.mark.anyio
async def test_initial_load_success_first_attempt(baseline_holder: RuntimeConfigHolder) -> None:
    """İlk denemede başarılı yüklemeyi doğrular."""
    class GoodClient(ConfigServerClient):
        def __init__(self) -> None:
            pass
        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            return [{"name": "ok.yaml", "source": {"ai.agent.max-steps": 2}}]

    ok = await initial_load(baseline_holder, GoodClient(), "ai-assistant-service", "dev", attempts=3)
    assert ok is True
    assert baseline_holder.current.agent.max_steps == 2


@pytest.mark.anyio
async def test_initial_load_retry_on_network_error(baseline_holder: RuntimeConfigHolder) -> None:
    """Ağ hatalarında backoff ile tekrar denenip başarılı olunduğunu doğrular."""
    calls = 0

    class TransientClient(ConfigServerClient):
        def __init__(self) -> None:
            pass
        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ConfigServerError("Geçici ağ kesintisi")
            return [{"name": "ok.yaml", "source": {"ai.agent.max-steps": 3}}]

    ok = await initial_load(
        baseline_holder,
        TransientClient(),
        "ai-assistant-service",
        "dev",
        attempts=3,
        backoff_sec=0.01,
    )
    assert ok is True
    assert calls == 3
    assert baseline_holder.current.agent.max_steps == 3


@pytest.mark.anyio
async def test_initial_load_all_attempts_fail(baseline_holder: RuntimeConfigHolder) -> None:
    """Tüm denemeler ağ hatası aldığında False döndüğünü ve belirtilen deneme kadar çağrıldığını doğrular."""
    calls = 0

    class FailingClient(ConfigServerClient):
        def __init__(self) -> None:
            pass
        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            nonlocal calls
            calls += 1
            raise ConfigServerError("Ulaşılamıyor")

    ok = await initial_load(
        baseline_holder,
        FailingClient(),
        "ai-assistant-service",
        "dev",
        attempts=3,
        backoff_sec=0.01,
    )
    assert ok is False
    assert calls == 3


@pytest.mark.anyio
async def test_initial_load_stops_immediately_on_validation_error(baseline_holder: RuntimeConfigHolder) -> None:
    """Bozuk şema/doğrulama hatasında tekrar denemenin anlamsız olduğunu ve ilk denemede durduğunu doğrular."""
    calls = 0

    class BadSchemaClient(ConfigServerClient):
        def __init__(self) -> None:
            pass
        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            nonlocal calls
            calls += 1
            return [{"name": "bad.yaml", "source": {"ai.agent.max-steps": "cok_fazla"}}]

    ok = await initial_load(
        baseline_holder,
        BadSchemaClient(),
        "ai-assistant-service",
        "dev",
        attempts=5,
        backoff_sec=0.01,
    )
    assert ok is False
    # Format/doğrulama hatasında 5 kez denememeli, 1. denemede durmalı
    assert calls == 1
    assert baseline_holder.status.last_error == "validation"


@pytest.mark.anyio
async def test_initial_load_succeeds_when_config_is_identical_to_baseline(
    baseline_holder: RuntimeConfigHolder,
) -> None:
    """Config Server baseline ile aynı ayarları döndüğünde tek denemede başarılı (True) olmalıdır."""
    calls = 0

    class IdenticalClient(ConfigServerClient):
        def __init__(self) -> None:
            pass

        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            nonlocal calls
            calls += 1
            return [{"name": "app.yaml", "source": {"ai.agent.max-steps": baseline_holder.current.agent.max_steps}}]

    ok = await initial_load(
        baseline_holder,
        IdenticalClient(),
        "ai-assistant-service",
        "dev",
        attempts=3,
        backoff_sec=0.01,
    )
    assert ok is True
    assert calls == 1
    assert baseline_holder.status.last_error is None
    assert baseline_holder.status.consecutive_failures == 0
    assert baseline_holder.status.source == "config-server"

