"""Pytest root configuration and global fixtures for ai-assistant-service."""

from collections.abc import Generator
from typing import Any
import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def disable_gateway_security_for_tests() -> Generator[None, None, None]:
    """Disable gateway secret validation by default for general unit/api tests.

    Security-specific tests in tests/core/test_security.py and tests/api/test_agent.py
    can explicitly enable it or supply valid headers.
    """
    original_state = settings.GATEWAY_SECURITY_ENABLED
    settings.GATEWAY_SECURITY_ENABLED = False
    try:
        yield
    finally:
        settings.GATEWAY_SECURITY_ENABLED = original_state


@pytest.fixture(autouse=True)
def disable_config_server_for_tests() -> Generator[None, None, None]:
    """Birim testleri sırasında gerçek Config Server'a ağ çağrısı yapılmasını varsayılan olarak engeller.

    Config Server'ı test eden testler monkeypatch ile CONFIG_SERVER_ENABLED=True yapıp
    MockTransport sağlayabilir.
    """
    original_state = settings.CONFIG_SERVER_ENABLED
    settings.CONFIG_SERVER_ENABLED = False
    try:
        yield
    finally:
        settings.CONFIG_SERVER_ENABLED = original_state


@pytest.fixture
def runtime_override():
    """app.state.runtime_config'i verilen bölüm değerleriyle geçici olarak değiştirir."""
    from app.main import app
    from app.runtimeconfig.holder import RuntimeConfigHolder
    from app.runtimeconfig.models import RuntimeSettings
    old = getattr(app.state, "runtime_config", None)

    def _apply(**sections: dict[str, Any]) -> None:
        tree = RuntimeSettings.from_startup(settings).model_dump()
        for name, values in sections.items():
            tree[name].update(values)
        app.state.runtime_config = RuntimeConfigHolder(RuntimeSettings.model_validate(tree), frozenset())

    yield _apply
    app.state.runtime_config = old
