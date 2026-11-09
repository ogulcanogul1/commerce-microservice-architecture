"""POST /actuator/refresh ve /health konfigürasyon durumu testleri."""

from typing import Any
from fastapi.testclient import TestClient
import httpx
import pytest

from app.core.config import Settings
from app.main import app
from app.runtimeconfig.client import ConfigServerClient
from app.runtimeconfig.holder import RuntimeConfigHolder
from app.runtimeconfig.models import RuntimeSettings


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


def test_actuator_refresh_not_initialized(test_client: TestClient) -> None:
    """Config Server istemcisi veya holder kurulmadığında 503 döndüğünü doğrular."""
    old_holder = getattr(app.state, "runtime_config", None)
    old_client = getattr(app.state, "config_server_client", None)
    app.state.runtime_config = None
    app.state.config_server_client = None

    try:
        response = test_client.post("/actuator/refresh")
        assert response.status_code == 503
        assert "Config Server" in response.json()["detail"]
    finally:
        app.state.runtime_config = old_holder
        app.state.config_server_client = old_client


def test_actuator_refresh_success_returns_changed_keys(test_client: TestClient) -> None:
    """Yenileme başarılı olduğunda değişen anahtarların Spring listesi olarak döndüğünü doğrular."""
    baseline = RuntimeSettings.from_startup(Settings(_env_file=None))
    holder = RuntimeConfigHolder(baseline, frozenset())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "name": "ai-assistant-service",
                "profiles": ["dev"],
                "propertySources": [
                    {
                        "name": "ai-assistant-service.yaml",
                        "source": {
                            "ai.agent.max-steps": 2,
                            "ai.rag.top-k": 10,
                        },
                    }
                ],
            },
        )

    mock_client = ConfigServerClient("http://localhost:8888/", transport=httpx.MockTransport(handler))

    old_holder = getattr(app.state, "runtime_config", None)
    old_client = getattr(app.state, "config_server_client", None)
    app.state.runtime_config = holder
    app.state.config_server_client = mock_client

    try:
        # 1. İlk yenileme: 2 anahtar değişmeli
        resp = test_client.post("/actuator/refresh")
        assert resp.status_code == 200
        changed = resp.json()
        assert "ai.agent.max-steps" in changed
        assert "ai.rag.top-k" in changed
        assert holder.current.agent.max_steps == 2
        assert holder.current.rag.top_k == 10

        # 2. İkinci yenileme (değişiklik yok): boş liste dönmeli []
        resp2 = test_client.post("/actuator/refresh")
        assert resp2.status_code == 200
        assert resp2.json() == []
    finally:
        app.state.runtime_config = old_holder
        app.state.config_server_client = old_client


def test_actuator_refresh_failure_returns_503(test_client: TestClient) -> None:
    """Config Server'a erişilemediğinde POST /actuator/refresh 503 dönmelidir."""
    baseline = RuntimeSettings.from_startup(Settings(_env_file=None))
    holder = RuntimeConfigHolder(baseline, frozenset())

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    mock_client = ConfigServerClient("http://localhost:8888/", transport=httpx.MockTransport(failing_handler))

    old_holder = getattr(app.state, "runtime_config", None)
    old_client = getattr(app.state, "config_server_client", None)
    app.state.runtime_config = holder
    app.state.config_server_client = mock_client

    try:
        resp = test_client.post("/actuator/refresh")
        assert resp.status_code == 503
        assert "yenileme başarısız" in resp.json()["detail"]
    finally:
        app.state.runtime_config = old_holder
        app.state.config_server_client = old_client



def test_health_endpoint_exposes_config_metadata(test_client: TestClient) -> None:
    """GET /health endpoint'inin config durumunu ve metadata'sını şeffafça döndüğünü doğrular."""
    baseline = RuntimeSettings.from_startup(Settings(_env_file=None))
    holder = RuntimeConfigHolder(baseline, frozenset({"agent.max_steps"}))

    old_holder = getattr(app.state, "runtime_config", None)
    app.state.runtime_config = holder

    try:
        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "UP"
        assert "config" in data
        cfg = data["config"]
        assert cfg["source"] == "env"
        assert len(cfg["version"]) == 12
        assert cfg["consecutive_failures"] == 0
        assert cfg["pinned"] == ["agent.max_steps"]
    finally:
        app.state.runtime_config = old_holder
