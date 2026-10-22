from unittest.mock import AsyncMock
import pytest

from app.core.pii_masker import PIIMasker
from app.llm.base import ChatMessage
from app.memory.rag_engine import rag_engine
from app.memory.session_store import RedisSessionStore
from app.tools import tool_registry


def test_pii_masker_redacts_credit_card_tckn_iban_and_secrets():
    raw_input = (
        "Merhaba, kart numaram 4543-1234-5678-9012, TCKN 12345678901, "
        "iade için IBAN TR33 0006 1005 1978 6457 8413 26 ve şifrem: SuperSecret99"
    )
    result = PIIMasker.mask_text(raw_input)

    assert result.was_masked is True
    assert "4543-1234-5678-9012" not in result.masked_text
    assert "12345678901" not in result.masked_text
    assert "TR33" not in result.masked_text
    assert "SuperSecret99" not in result.masked_text
    assert "[MASKED_CARD]" in result.masked_text
    assert "[MASKED_TCKN]" in result.masked_text
    assert "[MASKED_IBAN]" in result.masked_text
    assert "[MASKED_SECRET]" in result.masked_text
    assert set(result.detected_types) == {"IBAN", "CREDIT_CARD", "TCKN", "SECRET"}


@pytest.mark.asyncio
async def test_redis_session_store_sliding_window_and_ttl():
    mock_redis = AsyncMock()
    storage: dict[str, str] = {}

    async def fake_get(key: str):
        return storage.get(key)

    async def fake_set(key: str, val: str, ex: int = 1800):
        storage[key] = val

    async def fake_delete(key: str):
        storage.pop(key, None)

    mock_redis.get.side_effect = fake_get
    mock_redis.set.side_effect = fake_set
    mock_redis.delete.side_effect = fake_delete

    store = RedisSessionStore(redis_client=mock_redis, ttl_seconds=1800, max_window_messages=3)
    user_id = "user-101"
    session_id = "sess-abc"

    await store.append_messages(
        user_id,
        session_id,
        [
            ChatMessage(role="user", content="Mesaj 1"),
            ChatMessage(role="assistant", content="Yanıt 1"),
            ChatMessage(role="user", content="Mesaj 2"),
            ChatMessage(role="assistant", content="Yanıt 2"),
        ],
    )

    history = await store.get_history(user_id, session_id)
    # Sliding window of 3 keeps the latest 3 messages
    assert len(history) == 3
    assert [m.content for m in history] == ["Yanıt 1", "Mesaj 2", "Yanıt 2"]
    mock_redis.expire.assert_awaited_with("chat:session:user-101:sess-abc", 1800)

    await store.clear_session(user_id, session_id)
    assert await store.get_history(user_id, session_id) == []


@pytest.mark.asyncio
async def test_rag_engine_semantic_discovery_and_return_policy():
    # Scenario C.1: Pet-friendly low-light plant discovery
    plant_results = await tool_registry.execute(
        "search_policy_and_product_knowledge",
        {"query": "Karanlık bir odada solmayacak ve kediye zarar vermeyen ev bitkisi arıyorum."},
    )
    assert plant_results["resultCount"] >= 1
    top_plant_doc = plant_results["documents"][0]
    assert top_plant_doc["docId"] == "CAT-PLANTS-04"
    assert "Calathea Medallion" in top_plant_doc["content"]
    assert "Areka Palmiyesi" in top_plant_doc["content"]

    # Scenario D.2: Hygiene return policy for opened in-ear headphones
    hygiene_results = rag_engine.search(
        "Kulak içi kulaklığın ambalajını açtım ama kulağıma tam oturmadı, hijyen sebebiyle iade edemez miyim?"
    )
    assert len(hygiene_results) >= 1
    assert hygiene_results[0]["docId"] == "POL-HYGIENE-01"
    assert "yetkili servis" in hygiene_results[0]["content"]
