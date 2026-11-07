"""Integration test for Agent inquiry with real LLM provider and mock downstream microservice.

Plan Adım 7:
Gerçek LLM + sahte downstream ile 'ORD-... siparişim nerede?' -> kind='answer' ve cevapta durum;
anahtar yoksa pytest.skip.
"""

from __future__ import annotations

import httpx
import pytest

from app.agent.service import AgentService
from app.agent.tools.orders import GetOrderTool, ListMyOrdersTool
from app.agent.tools.registry import ToolRegistry
from app.clients.order import OrderClient
from app.core.config import settings
from app.core.security import RequestContext
from app.llm.factory import LLMFactory

USER_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.integration
@pytest.mark.anyio
async def test_order_status_inquiry_with_real_llm() -> None:
    # 1. API Anahtarı kontrolü: Gemini veya OpenAI anahtarı yoksa testi atla
    provider_name = (settings.AGENT_LLM_PROVIDER or settings.DEFAULT_LLM_PROVIDER or "gemini").lower()
    if provider_name == "gemini" and not settings.GEMINI_API_KEY:
        pytest.skip("GEMINI_API_KEY is not configured; skipping real LLM integration test.")
    elif provider_name == "openai" and not settings.OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY is not configured; skipping real LLM integration test.")
    elif not (settings.GEMINI_API_KEY or settings.OPENAI_API_KEY):
        pytest.skip("No real LLM API key configured; skipping live integration test.")

    # 2. Gerçek LLM sağlayıcısını başlat
    try:
        real_llm = LLMFactory.get_provider(
            provider_name=settings.AGENT_LLM_PROVIDER or None,
            model_name=settings.AGENT_LLM_MODEL or None,
        )
    except Exception as exc:
        pytest.skip(f"Real LLM provider could not be initialized: {exc}")

    # 3. Sahte downstream transport kur (ORD-999 siparişi SHIPPED durumunda)
    order_data = {
        "orderNumber": "ORD-999",
        "customerId": USER_ID,
        "status": "SHIPPED",
        "totalAmount": 1250.00,
        "currency": "TRY",
        "orderItems": [
            {
                "productCode": "PRD-1",
                "productName": "Kablosuz Kulaklık",
                "quantity": 1,
                "unitPrice": 1250.00,
            }
        ],
    }

    def order_mock_handler(request: httpx.Request) -> httpx.Response:
        url_path = request.url.path
        if "ORD-999" in url_path:
            return httpx.Response(200, json=order_data)
        if "/by-customer" in url_path or "/orders" in url_path:
            return httpx.Response(200, json=[order_data])
        return httpx.Response(404, json={"message": "Not found"})

    transport = httpx.MockTransport(order_mock_handler)
    order_client = OrderClient(
        base_url="http://mock-order-service",
        transport=transport,
    )

    registry = ToolRegistry()
    registry.register(GetOrderTool(order_client))
    registry.register(ListMyOrdersTool(order_client))

    agent_service = AgentService(
        llm=real_llm,
        registry=registry,
        max_steps=4,
    )

    ctx = RequestContext(
        user_id=USER_ID,
        correlation_id="corr-integ-test-999",
    )

    try:
        reply = await agent_service.chat("ORD-999 siparişim nerede?", ctx)
        assert reply.kind == "answer"
        assert len(reply.reply) > 0
        reply_lower = reply.reply.lower()
        # Yanıtta durum veya kargo bilgisi yer almalı
        assert any(term in reply_lower for term in ["kargo", "sevk", "gönder", "shipped", "yol", "hazır", "ord-999"])
    finally:
        await order_client.close()
