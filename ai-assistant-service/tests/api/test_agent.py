"""Tests for Agent API endpoints (POST /agent/chat, confirm, reject).

Covers:
1. Security & Context (401 on missing/invalid user_id, 403 on missing gateway secret).
2. Input Validation (422 on empty, whitespace, >1000 chars, invalid action_id regex).
3. Chat turn responses (kind="answer", "policy_answer", "abstained", "pending_action").
4. Action lifecycle: proposal -> confirm -> execute -> single-use replay 404.
5. Cross-user isolation: user B cannot confirm/reject user A's action.
6. Rejection flow: reject -> confirm returns 404.
7. Information hygiene: response body has no usage, steps, or leaked exceptions (503).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import uuid
import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent.executor import ActionExecutor
from app.agent.models import ActionType, AgentReply, PendingAction
from app.agent.pending import InMemoryPendingActionStore
from app.agent.service import AgentService
from app.agent.tickets import LoggingTicketPublisher
from app.agent.tools.actions import RequestOrderCancellationTool, RequestSupportTicketTool
from app.agent.tools.orders import GetOrderTool
from app.agent.tools.policy import SearchPolicyTool
from app.agent.tools.registry import ToolRegistry
from app.api.answer import AnswerResponse, CitationResponse
from app.clients.order import OrderClient
from app.core.config import settings
from app.llm.base import ChatMessage, LLMResponse, ToolCallRequest
from app.llm.fake import FakeLLMProvider
from app.main import app

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def test_app_state():
    """Backup and restore app.state properties for clean isolation."""
    old_service = getattr(app.state, "agent_service", None)
    old_store = getattr(app.state, "action_store", None)
    old_executor = getattr(app.state, "action_executor", None)
    yield
    app.state.agent_service = old_service
    app.state.action_store = old_store
    app.state.action_executor = old_executor


@pytest.fixture
def test_client(test_app_state):
    """TestClient without lifespan network side-effects."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ============================================================================
# 1. GÜVENLİK VE BAŞLIK DOĞRULAMA TESTLERİ
# ============================================================================


def test_chat_missing_user_id_returns_401(test_client: TestClient):
    """X-User-Id başlığı yoksa 401 Unauthorized dönmelidir."""
    resp = test_client.post("/agent/chat", json={"message": "Merhaba"})
    assert resp.status_code == 401
    assert "Kimlik" in resp.json()["detail"]


def test_chat_invalid_user_id_returns_401(test_client: TestClient):
    """X-User-Id geçerli bir UUIDv4 değilse 401 dönmelidir."""
    resp = test_client.post(
        "/agent/chat",
        headers={"X-User-Id": "not-a-valid-uuid"},
        json={"message": "Merhaba"},
    )
    assert resp.status_code == 401


def test_chat_gateway_security_enforced_returns_403(test_client: TestClient):
    """Gateway security aktifken geçersiz secret 403 Forbidden dönmelidir."""
    old_enabled = settings.GATEWAY_SECURITY_ENABLED
    old_secret = settings.GATEWAY_INTERNAL_SECRET
    settings.GATEWAY_SECURITY_ENABLED = True
    settings.GATEWAY_INTERNAL_SECRET = "super-secret-key"
    try:
        resp = test_client.post(
            "/agent/chat",
            headers={"X-User-Id": USER_A, "X-Gateway-Secret": "wrong-secret"},
            json={"message": "Merhaba"},
        )
        assert resp.status_code == 403
    finally:
        settings.GATEWAY_SECURITY_ENABLED = old_enabled
        settings.GATEWAY_INTERNAL_SECRET = old_secret


# ============================================================================
# 2. GİRDİ DOĞRULAMA (VALIDATION) TESTLERİ
# ============================================================================


def test_chat_empty_and_whitespace_message_returns_422(test_client: TestClient):
    """Boş veya yalnızca boşluktan oluşan mesajlar 422 dönmelidir."""
    headers = {"X-User-Id": USER_A}

    resp1 = test_client.post("/agent/chat", headers=headers, json={"message": ""})
    assert resp1.status_code == 422

    resp2 = test_client.post("/agent/chat", headers=headers, json={"message": "    \n   "})
    assert resp2.status_code == 422


def test_chat_overlength_message_returns_422(test_client: TestClient):
    """1000 karakterden uzun mesajlar 422 dönmelidir."""
    headers = {"X-User-Id": USER_A}
    long_msg = "a" * 1001

    resp = test_client.post("/agent/chat", headers=headers, json={"message": long_msg})
    assert resp.status_code == 422


def test_action_id_invalid_regex_returns_422(test_client: TestClient):
    """action_id regex standardına uymuyorsa 422 dönmelidir."""
    headers = {"X-User-Id": USER_A}

    # Too short (< 16 chars)
    resp = test_client.post("/agent/actions/short_id/confirm", headers=headers)
    assert resp.status_code == 422

    # Invalid characters (contains special chars)
    resp2 = test_client.post(
        "/agent/actions/invalid$id$with$special$chars/confirm",
        headers=headers,
    )
    assert resp2.status_code == 422


# ============================================================================
# 3. CHAT CEVAP ÇEŞİTLERİ (HAPPY PATHS & HYGIENE)
# ============================================================================


def test_chat_happy_path_answer(test_client: TestClient):
    """Normal sohbet dönüşü kind='answer' üretir ve dahili alanları sızdırmaz."""
    fake_llm = FakeLLMProvider(responses=["Siparişiniz hazırlanıyor."])
    registry = ToolRegistry()
    service = AgentService(llm=fake_llm, registry=registry)
    app.state.agent_service = service

    resp = test_client.post(
        "/agent/chat",
        headers={"X-User-Id": USER_A},
        json={"message": "Siparişim ne durumda?"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "answer"
    assert data["reply"] == "Siparişiniz hazırlanıyor."
    assert data["citations"] == []
    assert data["pending_action"] is None

    # Güvenlik ve Hijyen: dahili sayaçlar ve alanlar yanıtta OLMAMALIDIR
    assert "usage" not in data
    assert "steps" not in data
    assert "user_id" not in data
    assert "tool_results" not in data


def test_chat_policy_answer_with_citations(test_client: TestClient):
    """SearchPolicyTool terminal cevabı kind='policy_answer' ve atıfları döner."""
    fake_rag = type("MockRag", (), {})()

    async def mock_answer(question: str, correlation_id: str | None = None):
        return AnswerResponse(
            status="answered",
            answer="İade süresi 14 gündür.",
            citations=[
                CitationResponse(
                    number=1,
                    chunk_id="chunk-1",
                    source_file="iade.pdf",
                    page_start=1,
                    page_end=1,
                )
            ],
        )

    fake_rag.answer = mock_answer

    registry = ToolRegistry()
    registry.register(SearchPolicyTool(fake_rag))

    fake_llm = FakeLLMProvider(
        responses=[
            [
                ToolCallRequest(
                    call_id="call_policy_1",
                    tool_name="search_policy",
                    arguments={},
                )
            ]
        ]
    )
    service = AgentService(llm=fake_llm, registry=registry)
    app.state.agent_service = service

    resp = test_client.post(
        "/agent/chat",
        headers={"X-User-Id": USER_A},
        json={"message": "İade süresi ne kadar?"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "policy_answer"
    assert data["reply"] == "İade süresi 14 gündür."
    assert len(data["citations"]) == 1
    assert data["citations"][0]["source_file"] == "iade.pdf"


def test_chat_policy_abstained(test_client: TestClient):
    """Politika dokümanlarında bulunamayan sorgularda kind='abstained' döner."""
    fake_rag = type("MockRag", (), {})()

    async def mock_answer(question: str, correlation_id: str | None = None):
        return AnswerResponse(
            status="abstained",
            answer="Dokümanlarımızda bu bilgiye ulaşılamadı.",
            abstain_reason="no_results",
            citations=[],
        )

    fake_rag.answer = mock_answer

    registry = ToolRegistry()
    registry.register(SearchPolicyTool(fake_rag))

    fake_llm = FakeLLMProvider(
        responses=[
            [
                ToolCallRequest(
                    call_id="call_policy_2",
                    tool_name="search_policy",
                    arguments={},
                )
            ]
        ]
    )
    service = AgentService(llm=fake_llm, registry=registry)
    app.state.agent_service = service

    resp = test_client.post(
        "/agent/chat",
        headers={"X-User-Id": USER_A},
        json={"message": "Bilinmeyen kural nedir?"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "abstained"
    assert "ulaşılamadı" in data["reply"]


# ============================================================================
# 4. AKSİYON YAŞAM DÖNGÜSÜ (PROPOSAL -> CONFIRM -> EXECUTE -> REPLAY DEFENSE)
# ============================================================================


def test_cancellation_flow_end_to_end(test_client: TestClient):
    """İptal akışı: Chat ile pending_action oluşur, onaylanır, mock sipariş iptal edilir."""
    recorded_downstream_calls: list[str] = []

    def mock_order_handler(request: httpx.Request) -> httpx.Response:
        recorded_downstream_calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/api/v1/orders/by-number/ORD-101":
            return httpx.Response(
                200,
                json={
                    "id": "101",
                    "orderNumber": "ORD-101",
                    "customerId": USER_A,
                    "status": "PAID",
                    "totalAmount": 150.0,
                    "items": [],
                    "createdAt": "2026-11-01T10:00:00Z",
                    "updatedAt": "2026-11-01T10:00:00Z",
                },
            )
        if request.url.path == "/api/v1/orders/101/cancel":
            return httpx.Response(
                200,
                json={
                    "id": "101",
                    "orderNumber": "ORD-101",
                    "customerId": USER_A,
                    "status": "CANCELLED",
                    "totalAmount": 150.0,
                    "items": [],
                    "createdAt": "2026-11-01T10:00:00Z",
                    "updatedAt": "2026-11-01T10:05:00Z",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_order_handler)
    order_client = OrderClient(base_url="http://order-test", transport=transport)
    action_store = InMemoryPendingActionStore()
    ticket_pub = LoggingTicketPublisher()
    action_executor = ActionExecutor(order_client=order_client, ticket_publisher=ticket_pub)

    registry = ToolRegistry()
    registry.register(RequestOrderCancellationTool(order_client=order_client, action_store=action_store))

    fake_llm = FakeLLMProvider(
        responses=[
            [
                ToolCallRequest(
                    call_id="call_cancel_1",
                    tool_name="request_order_cancellation",
                    arguments={"order_number": "ORD-101", "reason": "Vazgeçtim"},
                )
            ],
            "İptal isteğinizi aldım.",
        ]
    )
    service = AgentService(llm=fake_llm, registry=registry)

    app.state.agent_service = service
    app.state.action_store = action_store
    app.state.action_executor = action_executor

    headers_a = {"X-User-Id": USER_A}

    # 1. Chat adımı: Onay önerisi üretilir
    chat_resp = test_client.post(
        "/agent/chat",
        headers=headers_a,
        json={"message": "ORD-101 siparişimi iptal etmek istiyorum."},
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["kind"] == "pending_action"
    assert chat_data["pending_action"] is not None
    action_id = chat_data["pending_action"]["action_id"]
    assert chat_data["pending_action"]["action_type"] == "cancel_order"

    # Henüz downstream cancel çağrılmamış olmalıdır!
    assert "POST /api/v1/orders/101/cancel" not in recorded_downstream_calls

    # 2. İkinci kullanıcı (USER_B) onaylamaya çalışırsa -> 404 Not Found
    headers_b = {"X-User-Id": USER_B}
    steal_resp = test_client.post(f"/agent/actions/{action_id}/confirm", headers=headers_b)
    assert steal_resp.status_code == 404
    assert "POST /api/v1/orders/101/cancel" not in recorded_downstream_calls

    # 3. Hak sahibi kullanıcı (USER_A) onaylar -> 200 executed
    confirm_resp = test_client.post(f"/agent/actions/{action_id}/confirm", headers=headers_a)
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()
    assert confirm_data["status"] == "executed"
    assert "başarıyla iptal edildi" in confirm_data["message"]

    # Downstream POST /api/v1/orders/101/cancel tam 1 kez çağrılmış olmalıdır
    cancel_calls = [c for c in recorded_downstream_calls if c == "POST /api/v1/orders/101/cancel"]
    assert len(cancel_calls) == 1

    # 4. Replay Saldırısı: Aynı action_id tekrar onaylanamaz -> 404 Not Found
    replay_resp = test_client.post(f"/agent/actions/{action_id}/confirm", headers=headers_a)
    assert replay_resp.status_code == 404

    # Tekrar iptal çağrısı yapılmamış olmalıdır (tam 1 çağrıda kaldı)
    cancel_calls_after = [c for c in recorded_downstream_calls if c == "POST /api/v1/orders/101/cancel"]
    assert len(cancel_calls_after) == 1


def test_reject_action_flow(test_client: TestClient):
    """Kullanıcı işlemi reddettiğinde status='rejected' döner ve sonraki onay 404 olur."""
    action_store = InMemoryPendingActionStore()
    app.state.action_store = action_store

    from datetime import timedelta
    action = PendingAction(
        action_id="reject_test_act_12345",
        user_id=USER_A,
        action_type="cancel_order",
        summary="ORD-999 sipariş iptali onayı",
        params={"order_number": "ORD-999", "order_id": 999},
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    action_store.create(action)

    headers_a = {"X-User-Id": USER_A}

    # Reddetme
    reject_resp = test_client.post(
        f"/agent/actions/{action.action_id}/reject",
        headers=headers_a,
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    # Reddedilen aksiyon tekrar onaylanamaz -> 404
    confirm_resp = test_client.post(
        f"/agent/actions/{action.action_id}/confirm",
        headers=headers_a,
    )
    assert confirm_resp.status_code == 404


def test_expired_action_returns_404(test_client: TestClient):
    """Süresi dolmuş aksiyon onaylanamaz -> 404."""
    action_store = InMemoryPendingActionStore()
    app.state.action_store = action_store

    from datetime import timedelta
    past_action = PendingAction(
        action_id="expired_act_123456789",
        user_id=USER_A,
        action_type="cancel_order",
        summary="Süresi dolmuş iptal",
        params={"order_number": "ORD-EXPIRED"},
        created_at=datetime.now(timezone.utc) - timedelta(seconds=100),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    action_store.create(past_action)

    headers_a = {"X-User-Id": USER_A}
    resp = test_client.post(f"/agent/actions/{past_action.action_id}/confirm", headers=headers_a)
    assert resp.status_code == 404


# ============================================================================
# 5. HATA EŞLEMESİ VE GÜVENLİ BİLGİ İZOLASYONU (503)
# ============================================================================


def test_chat_unconfigured_service_returns_503(test_client: TestClient):
    """app.state.agent_service None ise 503 dönmelidir."""
    app.state.agent_service = None

    resp = test_client.post(
        "/agent/chat",
        headers={"X-User-Id": USER_A},
        json={"message": "Merhaba"},
    )
    assert resp.status_code == 503
    assert "yapılandırılmamış" in resp.json()["detail"]


def test_chat_timeout_returns_503(test_client: TestClient):
    """LLM zaman aşımı 503 dönmeli ve temiz mesaj verilmelidir."""
    mock_service = type("MockService", (), {})()

    async def timeout_chat(message: str, ctx):
        raise asyncio.TimeoutError()

    mock_service.chat = timeout_chat
    app.state.agent_service = mock_service

    resp = test_client.post(
        "/agent/chat",
        headers={"X-User-Id": USER_A},
        json={"message": "Merhaba"},
    )
    assert resp.status_code == 503
    assert "zaman aşımına" in resp.json()["detail"]


def test_chat_internal_error_does_not_leak_secrets(test_client: TestClient):
    """İç exception mesajı (ör. API token veya gizli değer) yanıt gövdesine sızmamalıdır."""
    mock_service = type("MockService", (), {})()

    async def fail_chat(message: str, ctx):
        raise RuntimeError("CRITICAL_API_SECRET_TOKEN_XYZ_12345")

    mock_service.chat = fail_chat
    app.state.agent_service = mock_service

    resp = test_client.post(
        "/agent/chat",
        headers={"X-User-Id": USER_A},
        json={"message": "Merhaba"},
    )
    assert resp.status_code == 503
    body = resp.text
    assert "CRITICAL_API_SECRET_TOKEN_XYZ_12345" not in body
    assert "Cevap üretilirken bir hata oluştu." in body


def test_chat_rag_infrastructure_failure_returns_503(test_client: TestClient):
    """Qdrant veya RAG altyapı kesintisi model hatası olarak gizlenmemeli, 503 dönmelidir."""
    mock_rag = type("MockRag", (), {})()

    async def fail_rag(*args, **kwargs):
        raise RuntimeError("Qdrant down")

    mock_rag.answer = fail_rag

    registry = ToolRegistry()
    registry.register(SearchPolicyTool(rag_service=mock_rag))

    fake_llm = FakeLLMProvider(
        responses=[
            [
                ToolCallRequest(
                    call_id="call-policy-1",
                    tool_name="search_policy",
                    arguments={},
                )
            ]
        ]
    )

    agent_service = AgentService(
        llm=fake_llm,
        registry=registry,
    )
    app.state.agent_service = agent_service

    resp = test_client.post(
        "/agent/chat",
        headers={"X-User-Id": USER_A},
        json={"message": "İade sürem kaç gün?"},
    )
    assert resp.status_code == 503
    assert "Cevap üretilirken bir hata oluştu." in resp.json()["detail"]


def test_api_v1_chat_route_resolves_and_responds(test_client: TestClient):
    """API Gateway üzerinden gelen /api/v1/chat rotası doğru çözümlenmeli ve yanıt dönmelidir."""
    fake_llm = FakeLLMProvider(responses=["Merhaba, size nasıl yardımcı olabilirim?"])
    registry = ToolRegistry()
    service = AgentService(llm=fake_llm, registry=registry)
    app.state.agent_service = service

    # 1. POST /api/v1/chat
    resp1 = test_client.post(
        "/api/v1/chat",
        headers={"X-User-Id": USER_A},
        json={"message": "Merhaba"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["reply"] == "Merhaba, size nasıl yardımcı olabilirim?"

    # 2. POST /api/v1/chat/chat
    fake_llm.responses.append("Tekrar merhaba!")
    resp2 = test_client.post(
        "/api/v1/chat/chat",
        headers={"X-User-Id": USER_A},
        json={"message": "Merhaba 2"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["reply"] == "Tekrar merhaba!"


def test_confirm_action_restores_store_on_downstream_failure(test_client: TestClient):
    """Downstream kesintisinde tüketilen aksiyon depoya geri yüklenmeli ve 503 dönmelidir."""
    from datetime import timedelta
    from app.clients.base import DownstreamUnavailable
    from app.agent.models import ExecutionResult

    now = datetime.now(timezone.utc)
    store = InMemoryPendingActionStore()
    action = PendingAction(
        action_id="act-failover-test-12345",
        user_id=USER_A,
        action_type="cancel_order",
        params={"order_number": "ORD-DOWN-1"},
        summary="Sipariş iptali onayı",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    store.create(action)

    call_count = 0

    class FlakyExecutor:
        async def execute(self, act, context):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # İlk çağrıda downstream kesintisi
                raise DownstreamUnavailable("Order service connection refused")
            # İkinci çağrıda başarılı
            return ExecutionResult(ok=True, message="Sipariş başarıyla iptal edildi.")

    app.state.action_store = store
    app.state.action_executor = FlakyExecutor()

    # 1. İlk deneme: Downstream kesintisi sebebiyle 503 dönmeli
    resp1 = test_client.post(
        f"/agent/actions/{action.action_id}/confirm",
        headers={"X-User-Id": USER_A},
    )
    assert resp1.status_code == 503
    assert "lütfen kısa süre sonra tekrar deneyin" in resp1.json()["detail"]

    # Aksiyon depodan silinmemiş (geri yüklenmiş) olmalı
    # 2. İkinci deneme (retry): Başarılı olmalı
    resp2 = test_client.post(
        f"/agent/actions/{action.action_id}/confirm",
        headers={"X-User-Id": USER_A},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "executed"
    assert resp2.json()["message"] == "Sipariş başarıyla iptal edildi."

    # 3. Üçüncü deneme: Başarılı tüketimden sonra artık 404 dönmeli (replay koruması)
    resp3 = test_client.post(
        f"/agent/actions/{action.action_id}/confirm",
        headers={"X-User-Id": USER_A},
    )
    assert resp3.status_code == 404
