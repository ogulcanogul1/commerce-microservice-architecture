from typing import AsyncGenerator
from unittest.mock import patch
from fastapi.testclient import TestClient
import httpx

from app.core.config import settings
from app.core.security import GATEWAY_SECRET_HEADER, USER_EMAIL_HEADER, USER_ID_HEADER
from app.llm.base import (
    AgentResponse,
    BaseLLMProvider,
    ChatMessage,
    ToolCallRequest,
    ToolDefinition,
)
from app.main import app
from app.tools import CommerceHttpClient, set_http_client

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
ORDER_ID = "22222222-2222-2222-2222-222222222222"


class FakeReActLLMProvider(BaseLLMProvider):
    """Simulates a 2-step ReAct loop: first calls get_shipment_tracking, then synthesizes final Turkish answer."""

    provider_name = "claude"
    model_name = "claude-3-5-sonnet-latest"

    def __init__(self) -> None:
        self.call_count = 0
        self.received_messages: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.2,
    ) -> AgentResponse:
        self.call_count += 1
        self.received_messages.append(list(messages))

        if self.call_count == 1:
            return AgentResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="call_track_1",
                        tool_name="get_shipment_tracking",
                        arguments={"order_identifier": "ORD-9912"},
                    )
                ],
                finish_reason="tool_calls",
                provider_used=self.provider_name,
                model_used=self.model_name,
            )

        return AgentResponse(
            content=(
                "Son siparişiniz (#ORD-9912) Aras Kargo ile dağıtımda (Takip No: TRK-4421). "
                "Tahmini teslimat saati bugün 16:30."
            ),
            tool_calls=[],
            finish_reason="stop",
            provider_used=self.provider_name,
            model_used=self.model_name,
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.2,
    ) -> AsyncGenerator[str, None]:
        yield "Test "


def _setup_downstream_mock() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/orders/by-number/ORD-9912":
            return httpx.Response(
                200,
                json={
                    "id": ORDER_ID,
                    "orderNumber": "ORD-9912",
                    "customerId": CUSTOMER_ID,
                    "status": "SHIPPING_CREATED",
                },
            )
        if request.url.path == f"/api/v1/shipments/order/{ORDER_ID}":
            return httpx.Response(
                200,
                json={
                    "id": "ship-1",
                    "orderId": ORDER_ID,
                    "trackingNumber": "TRK-4421",
                    "carrier": "ARAS",
                    "status": "IN_TRANSIT",
                    "estimatedDelivery": "2026-10-22T16:30:00Z",
                },
            )
        if request.url.path == "/api/v1/shipments/track/TRK-4421":
            return httpx.Response(
                200,
                json={
                    "trackingNumber": "TRK-4421",
                    "carrier": "ARAS",
                    "currentStatus": "IN_TRANSIT",
                    "estimatedDelivery": "2026-10-22T16:30:00Z",
                    "history": [{"status": "IN_TRANSIT", "description": "Dağıtımda"}],
                },
            )
        return httpx.Response(404)

    set_http_client(CommerceHttpClient(transport=httpx.MockTransport(handler)))


def _auth_headers() -> dict[str, str]:
    return {
        GATEWAY_SECRET_HEADER: settings.GATEWAY_INTERNAL_SECRET,
        USER_ID_HEADER: CUSTOMER_ID,
        USER_EMAIL_HEADER: "ayse@example.com",
    }


def test_post_chat_executes_react_loop_masks_pii_and_persists_session():
    _setup_downstream_mock()
    fake_provider = FakeReActLLMProvider()
    client = TestClient(app)

    with patch("app.services.agent_orchestrator.LLMFactory.get_provider", return_value=fake_provider):
        response = client.post(
            "/api/v1/chat",
            headers=_auth_headers(),
            json={
                "session_id": "sess-e2e-01",
                "message": "Kartım 4543-1234-5678-9012, ORD-9912 numaralı kargom nerede ve kedi dostu bitki var mı?",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "sess-e2e-01"
    assert body["provider_used"] == "claude"
    assert body["pii_masked"] is True
    assert "CREDIT_CARD" in body["detected_pii_types"]
    assert "TRK-4421" in body["reply"]
    assert len(body["tools_executed"]) == 1
    assert body["tools_executed"][0]["tool_name"] == "get_shipment_tracking"
    assert "CAT-PLANTS-04" in body["rag_documents_used"]

    # Ensure raw credit card number never reached the LLM provider
    sent_user_text = fake_provider.received_messages[0][-1].content
    assert "4543-1234-5678-9012" not in sent_user_text
    assert "[MASKED_CARD]" in sent_user_text

    # Verify session history was persisted and can be retrieved & cleared
    hist_res = client.get("/api/v1/chat/sessions/sess-e2e-01", headers=_auth_headers())
    assert hist_res.status_code == 200
    assert hist_res.json()["messageCount"] == 2

    del_res = client.delete("/api/v1/chat/sessions/sess-e2e-01", headers=_auth_headers())
    assert del_res.status_code == 204


def test_post_chat_stream_sse_and_list_tools():
    _setup_downstream_mock()
    fake_provider = FakeReActLLMProvider()
    client = TestClient(app)

    with patch("app.services.agent_orchestrator.LLMFactory.get_provider", return_value=fake_provider):
        stream_res = client.post(
            "/api/v1/chat/stream",
            headers=_auth_headers(),
            json={
                "session_id": "sess-stream-01",
                "message": "ORD-9912 siparişim nerede?",
            },
        )
    assert stream_res.status_code == 200
    assert "text/event-stream" in stream_res.headers["content-type"]
    assert "data: [DONE]" in stream_res.text

    tools_res = client.get("/api/v1/chat/tools", headers=_auth_headers())
    assert tools_res.status_code == 200
    tools_body = tools_res.json()
    assert tools_body["toolCount"] >= 11
    assert "claude" in tools_body["supportedProviders"]
