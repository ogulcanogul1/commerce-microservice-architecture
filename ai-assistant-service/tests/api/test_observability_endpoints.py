"""Actuator Gözlemlenebilirlik ve Sağlık Denetimi Uç Noktaları Testleri.

Bu test modülü:
1. /actuator/prometheus endpoint'inin gateway secret gerektirmeden 200 döndüğünü ve metrikleri sunduğunu,
2. /actuator/refresh endpoint'inin ise secret olmadan 403 verdiğini (güvenlik ayrımı),
3. /actuator/health/liveness endpoint'inin her zaman 200 UP döndüğünü,
4. /actuator/health/readiness endpoint'inin startup, drain ve redis durumlarını Spring Boot uyumlu
   status kodlarıyla (200 UP / 503 OUT_OF_SERVICE) yansıttığını,
5. LLM sağlayıcısı tamamen çökse bile readiness'in 200 kalmaya devam ettiğini (LLM izolasyonu) doğrular.
"""

from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.observability import observability_router
from app.core.config import settings
from app.main import app as main_app


def test_actuator_prometheus_accessible_without_secret():
    """/actuator/prometheus endpoint'inin X-Gateway-Secret olmadan 200 döndüğünü ve

    tanımlı temel metrikleri içerdiğini doğrular.
    """
    client = TestClient(main_app)
    response = client.get("/actuator/prometheus")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")

    body = response.text
    # Histogram ve sayaç HELP/TYPE satırlarının çıktıda olduğunu doğrula
    assert "http_server_requests_seconds" in body
    assert "ai_tool_call_duration_seconds" in body
    assert "ai_llm_request_duration_seconds" in body
    assert "ai_llm_tokens_total" in body


def test_actuator_refresh_remains_protected_with_secret(monkeypatch: pytest.MonkeyPatch):
    """POST /actuator/refresh endpoint'inin gizli anahtar olmadan 403 Forbidden döndüğünü

    ve yeni router'dan bağımsız olarak korunduğunu doğrular.
    """
    monkeypatch.setattr(settings, "GATEWAY_SECURITY_ENABLED", True)
    client = TestClient(main_app)
    response = client.post("/actuator/refresh")
    # Gateway secret verilmediği için 403 ile reddedilmeli
    assert response.status_code == 403


def test_liveness_probe_always_returns_up():
    """/actuator/health/liveness endpoint'inin her zaman 200 {"status": "UP"} döndüğünü doğrular."""
    client = TestClient(main_app)
    response = client.get("/actuator/health/liveness")
    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_readiness_probe_lifecycle_states(monkeypatch: pytest.MonkeyPatch):
    """Readiness kontrolünün açılış, drain ve redis arızası durumlarındaki HTTP yanıtlarını doğrular."""
    test_app = FastAPI()
    test_app.include_router(observability_router)
    client = TestClient(test_app)

    # 1. Durum: Uygulama henüz başlatılmadı (app.state.ready yok) -> 503 OUT_OF_SERVICE
    test_app.state.ready = False
    test_app.state.draining = False
    resp1 = client.get("/actuator/health/readiness")
    assert resp1.status_code == 503
    assert resp1.json()["status"] == "OUT_OF_SERVICE"
    assert resp1.json()["components"]["startup"] == "DOWN"

    # 2. Durum: Uygulama hazır, drain yok, Redis kapalı -> 200 UP
    monkeypatch.setattr(settings, "REDIS_ENABLED", False)
    test_app.state.ready = True
    test_app.state.draining = False
    resp2 = client.get("/actuator/health/readiness")
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "UP"
    assert resp2.json()["components"]["startup"] == "UP"
    assert resp2.json()["components"]["drain"] == "UP"
    assert resp2.json()["components"]["redis"] == "DISABLED"

    # 3. Durum: SIGTERM alındı, drain modu aktif -> 503 OUT_OF_SERVICE
    test_app.state.draining = True
    resp3 = client.get("/actuator/health/readiness")
    assert resp3.status_code == 503
    assert resp3.json()["status"] == "OUT_OF_SERVICE"
    assert resp3.json()["components"]["drain"] == "DOWN"

    # 4. Durum: Redis aktif ama ping başarısız/hatalı -> 503 OUT_OF_SERVICE
    test_app.state.draining = False
    monkeypatch.setattr(settings, "REDIS_ENABLED", True)

    broken_redis = AsyncMock()
    broken_redis.ping.side_effect = ConnectionError("Redis unreachable")
    test_app.state.redis_client = broken_redis

    resp4 = client.get("/actuator/health/readiness")
    assert resp4.status_code == 503
    assert resp4.json()["status"] == "OUT_OF_SERVICE"
    assert resp4.json()["components"]["redis"] == "DOWN"

    # 5. Durum: REDIS_ENABLED=True ancak redis_client=None (Açılışta InMemory deposuna fallback yapıldı)
    # Servisin kalıcı olarak 503 OUT_OF_SERVICE'te kilitlenmesini önlemek için redis: DISABLED ve 200 UP dönmelidir
    test_app.state.redis_client = None
    resp5 = client.get("/actuator/health/readiness")
    assert resp5.status_code == 200
    assert resp5.json()["status"] == "UP"
    assert resp5.json()["components"]["redis"] == "DISABLED"


def test_readiness_probe_llm_outage_independence(monkeypatch: pytest.MonkeyPatch):
    """Dış LLM sağlayıcısı tamamen çökse bile readiness probunun 200 UP kaldığını

    (Plan 1.5 Altın Kuralı: LLM arızasının pod'u NotReady yapmaması) doğrular.
    """
    test_app = FastAPI()
    test_app.include_router(observability_router)
    client = TestClient(test_app)

    # Uygulama açılışını tamamlamış
    test_app.state.ready = True
    test_app.state.draining = False
    monkeypatch.setattr(settings, "REDIS_ENABLED", False)

    # Simüle edilmiş çökmüş LLM istemcisi
    broken_llm = AsyncMock()
    broken_llm.generate.side_effect = RuntimeError("OpenAI / Gemini API totally DOWN 500")
    test_app.state.llm_client = broken_llm

    # LLM tamamen çökse bile readiness kontrolü asla etkilenmemeli ve 200 dönmeli
    response = client.get("/actuator/health/readiness")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"
    # Components içinde asla LLM alanı olmamalıdır
    assert "llm" not in response.json()["components"]
