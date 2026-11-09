"""RuntimeConfigHolder birim testleri.

Canlı konfigürasyon deposunun (holder) tüm durum yönetimi, atomik swap,
doğrulama hatalarında son bilinen iyi config'i koruma, pinned alan üstünlüğü,
dinleyici bildirimleri ve snapshot değişmezliği test edilir.
"""

from typing import Any
import pytest

from app.core.config import Settings
from app.runtimeconfig.client import ConfigServerClient, ConfigServerError
from app.runtimeconfig.holder import RuntimeConfigHolder
from app.runtimeconfig.models import RuntimeSettings


@pytest.fixture
def baseline_settings() -> RuntimeSettings:
    """Temel Settings varsayılanlarından türetilmiş temiz RuntimeSettings nesnesi."""
    return RuntimeSettings.from_startup(Settings(_env_file=None))


def test_holder_initial_state(baseline_settings: RuntimeSettings) -> None:
    """Başlangıçta holder'ın kaynak olarak 'env' kullandığını ve sayaçların sıfır olduğunu doğrular."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset({"agent.max_steps"}))
    status = holder.status

    assert status.source == "env"
    assert status.consecutive_failures == 0
    assert status.last_error is None
    assert status.last_success_at is None
    assert status.pinned == ("agent.max_steps",)
    assert holder.current.agent.max_steps == baseline_settings.agent.max_steps


def test_apply_property_sources_success_and_listeners(baseline_settings: RuntimeSettings) -> None:
    """Geçerli bir propertySource uygulandığında atomik swap yapıldığını ve dinleyicinin çalıştığını doğrular."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset())
    captured_changes: list[tuple[RuntimeSettings, RuntimeSettings]] = []

    def sample_listener(old: RuntimeSettings, new: RuntimeSettings) -> None:
        captured_changes.append((old, new))

    holder.add_listener(sample_listener)

    sources = [
        {"name": "ai-assistant-service.yaml", "source": {"ai.agent.max-steps": 2, "ai.rag.top-k": 10}}
    ]

    changed = holder.apply_property_sources(sources)

    assert changed is True
    assert holder.current.agent.max_steps == 2
    assert holder.current.rag.top_k == 10
    assert holder.status.source == "config-server"
    assert holder.status.consecutive_failures == 0
    assert holder.status.last_success_at is not None

    # Dinleyici eski ve yeni nesnelerle tam 1 kez çağrılmış olmalı
    assert len(captured_changes) == 1
    old_rt, new_rt = captured_changes[0]
    assert old_rt.agent.max_steps == baseline_settings.agent.max_steps
    assert new_rt.agent.max_steps == 2


def test_apply_property_sources_idempotent_no_op(baseline_settings: RuntimeSettings) -> None:
    """Aynı konfigürasyon tekrar uygulandığında hash değişmediği için no-op yapıldığını doğrular."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset())
    sources = [{"name": "ai-assistant-service.yaml", "source": {"ai.agent.max-steps": 2}}]

    # İlk uygulama -> Değişiklik var (True)
    assert holder.apply_property_sources(sources) is True

    listener_called = False

    def should_not_run(old: RuntimeSettings, new: RuntimeSettings) -> None:
        nonlocal listener_called
        listener_called = True

    holder.add_listener(should_not_run)

    # İkinci uygulama -> Değişiklik yok (False), listener çalışmamalı
    assert holder.apply_property_sources(sources) is False
    assert listener_called is False


@pytest.mark.anyio
async def test_refresh_validation_failure_preserves_current_and_masks_input(
    baseline_settings: RuntimeSettings, caplog: pytest.LogCaptureFixture
) -> None:
    """Bozuk tip/değer geldiğinde current'ın korunduğunu ve loglarda kullanıcının ham değerinin gizlendiğini doğrular."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset())

    class FakeClient(ConfigServerClient):
        def __init__(self) -> None:
            pass
        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            return [{"name": "bad.yaml", "source": {"ai.agent.max-steps": "cok_fazla_adim"}}]

    with caplog.at_level("ERROR"):
        ok = await holder.refresh(FakeClient(), "ai-assistant-service", "dev")

    assert ok is False
    # Aktif config bozulmamalı
    assert holder.current.agent.max_steps == baseline_settings.agent.max_steps
    assert holder.status.last_error == "validation"
    assert holder.status.consecutive_failures == 1

    # Logda hata alanı geçmeli ama 'cok_fazla_adim' değeri sızmamalıdır (include_input=False)
    assert "agent.max_steps" in caplog.text
    assert "cok_fazla_adim" not in caplog.text


@pytest.mark.anyio
async def test_refresh_gateway_ceiling_violation_rejected(baseline_settings: RuntimeSettings) -> None:
    """Gateway TimeLimiter (65s) tavanını aşan ayarların reddedildiğini doğrular."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset())

    class CeilingClient(ConfigServerClient):
        def __init__(self) -> None:
            pass
        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            return [{"name": "bad.yaml", "source": {"ai.agent.turn-timeout-sec": 90.0}}]

    ok = await holder.refresh(CeilingClient(), "ai-assistant-service", "dev")
    assert ok is False
    assert holder.status.last_error == "validation"
    assert holder.current.agent.turn_timeout_sec == baseline_settings.agent.turn_timeout_sec


@pytest.mark.anyio
async def test_refresh_unknown_key_rejected(baseline_settings: RuntimeSettings) -> None:
    """extra='forbid' kuralı ile ai.* altında bilinmeyen anahtar geldiğinde reddedildiğini doğrular."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset())

    class UnknownKeyClient(ConfigServerClient):
        def __init__(self) -> None:
            pass
        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            return [{"name": "bad.yaml", "source": {"ai.redis.host": "remote-redis"}}]

    ok = await holder.refresh(UnknownKeyClient(), "ai-assistant-service", "dev")
    assert ok is False
    assert holder.status.last_error == "validation"


@pytest.mark.anyio
async def test_refresh_fetch_error_and_recovery(baseline_settings: RuntimeSettings) -> None:
    """Ağ hatasında last_error='fetch' olduğunu ve ardından başarılı çekmede sayaçların sıfırlandığını doğrular."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset())

    class FailingClient(ConfigServerClient):
        def __init__(self) -> None:
            pass
        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            raise ConfigServerError("Bağlantı koptu")

    # 1. Başarısızlık
    assert await holder.refresh(FailingClient(), "ai-assistant-service", "dev") is False
    assert holder.status.last_error == "fetch"
    assert holder.status.consecutive_failures == 1

    # 2. Başarısızlık
    assert await holder.refresh(FailingClient(), "ai-assistant-service", "dev") is False
    assert holder.status.consecutive_failures == 2

    # 3. İyileşme (Başarılı)
    class GoodClient(ConfigServerClient):
        def __init__(self) -> None:
            pass
        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            return [{"name": "ok.yaml", "source": {"ai.agent.max-steps": 3}}]

    assert await holder.refresh(GoodClient(), "ai-assistant-service", "dev") is True
    assert holder.status.consecutive_failures == 0
    assert holder.status.last_error is None
    assert holder.current.agent.max_steps == 3


@pytest.mark.anyio
async def test_refresh_succeeds_when_config_is_identical_to_baseline(baseline_settings: RuntimeSettings) -> None:
    """Config Server baseline ile birebir aynı değerleri dönse bile refresh başarılı (True) sayılmalıdır."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset())

    class IdenticalClient(ConfigServerClient):
        def __init__(self) -> None:
            pass

        async def fetch_property_sources(self, app_name: str, profile: str) -> list[dict[str, Any]]:
            return [{"name": "app.yaml", "source": {"ai.agent.max-steps": baseline_settings.agent.max_steps}}]

    ok = await holder.refresh(IdenticalClient(), "ai-assistant-service", "dev")
    assert ok is True
    assert holder.status.source == "config-server"
    assert holder.status.last_error is None
    assert holder.status.consecutive_failures == 0
    assert holder.status.last_success_at is not None



def test_pinned_path_wins_over_config_server(baseline_settings: RuntimeSettings) -> None:
    """Env ile sabitlenmiş (pinned) alanların Config Server değeriyle ezilemeyeceğini doğrular."""
    # agent.max_steps sabitlenmiş olsun (baseline değeri 4)
    holder = RuntimeConfigHolder(baseline_settings, frozenset({"agent.max_steps"}))

    sources = [
        {"name": "remote.yaml", "source": {"ai.agent.max-steps": 1, "ai.rag.top-k": 15}}
    ]

    holder.apply_property_sources(sources)

    # agent.max_steps env değeri olan 4 olarak kalmalı, rag.top_k ise server'dan 15 olmalı
    assert holder.current.agent.max_steps == baseline_settings.agent.max_steps
    assert holder.current.rag.top_k == 15


def test_key_removal_reverts_to_baseline(baseline_settings: RuntimeSettings) -> None:
    """Config Server'dan bir anahtar silindiğinde değerin baseline'a geri döndüğünü doğrular."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset())

    # Önce max-steps'i 2 yap
    holder.apply_property_sources([
        {"name": "remote.yaml", "source": {"ai.agent.max-steps": 2}}
    ])
    assert holder.current.agent.max_steps == 2

    # Ardından bu anahtarın bulunmadığı yeni bir yayın gelsin
    holder.apply_property_sources([
        {"name": "remote.yaml", "source": {"ai.rag.top-k": 10}}
    ])
    # max-steps baseline değerine geri dönmeli
    assert holder.current.agent.max_steps == baseline_settings.agent.max_steps
    assert holder.current.rag.top_k == 10


def test_listener_exception_does_not_abort_swap(baseline_settings: RuntimeSettings) -> None:
    """Bir dinleyici exception fırlatsa bile swap'ın geçerli kaldığını ve diğer dinleyicinin çalıştığını doğrular."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset())
    second_listener_called = False

    def faulty_listener(old: RuntimeSettings, new: RuntimeSettings) -> None:
        raise RuntimeError("Dinleyici çöktü")

    def safe_listener(old: RuntimeSettings, new: RuntimeSettings) -> None:
        nonlocal second_listener_called
        second_listener_called = True

    holder.add_listener(faulty_listener)
    holder.add_listener(safe_listener)

    sources = [{"name": "ok.yaml", "source": {"ai.agent.max-steps": 2}}]
    changed = holder.apply_property_sources(sources)

    assert changed is True
    assert holder.current.agent.max_steps == 2
    assert second_listener_called is True


def test_per_request_snapshot_immutability(baseline_settings: RuntimeSettings) -> None:
    """İstek başında alınan snapshot referansının, arka planda holder değişse bile değişmediğini doğrular."""
    holder = RuntimeConfigHolder(baseline_settings, frozenset())

    # Endpoint istek başında snapshot aldı
    snapshot = holder.current
    initial_steps = snapshot.agent.max_steps

    # Arka planda poller yeni config uyguladı
    holder.apply_property_sources([
        {"name": "remote.yaml", "source": {"ai.agent.max-steps": 1}}
    ])

    # Yeni istekler yeni değeri görür
    assert holder.current.agent.max_steps == 1
    # Ancak devam eden isteğin elindeki snapshot eski değeri korur
    assert snapshot.agent.max_steps == initial_steps
