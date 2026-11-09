"""Answer API birim testleri (POST /rag/answer).

Test Edilen Durumlar:
1. Başarılı Cevaplama (Happy Path - 200 OK): Doğru cevap, citations listesi ve metadata alanları.
2. Model Abstain (200 OK): LLM BULUNAMADI döndüğünde status="abstained", abstain_reason="model_abstained".
3. Alan İzolasyonu: validation_issues, usage, top_dense_score gibi dahili alanların yanıtta OLMAMASI.
4. Girdi Doğrulama (422 Unprocessable Entity):
   - Boş veya yalnızca boşluktan oluşan sorular.
   - 1000 karakterden uzun sorular.
   - k = 0 ve k = 11 sınır dışı değerleri.
5. Servis Erişilemezliği / Yapılandırma Hatası (503 Service Unavailable):
   - rag_answer_service app.state üzerinde yoksa.
   - Koleksiyon henüz indekslenmemişse.
   - TimeoutError durumunda iç hata mesajı sızdırılmadan 503.
   - RuntimeError ve beklenmeyen exception durumlarında hassas mesaj sızdırılmadan 503.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.api.answer import get_rag_answer_service
from app.api.search import get_embedder, get_qdrant_store
from app.llm.fake import FakeLLMProvider
from app.main import app
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.embedding.fake import FakeEmbedder
from app.rag.generation.models import GenerationConfig
from app.rag.generation.service import RagAnswerService
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.store import QdrantStore


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    """16 boyutlu deterministik sahte embedder."""
    return FakeEmbedder(dimensions=16)


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    """Testler için kontrol edilebilir sahte LLM sağlayıcısı."""
    return FakeLLMProvider(
        responses=[
            "İade süresi 14 gündür [1].",
        ]
    )


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    """Test için örnek doküman parçaları."""
    return [
        Chunk(
            id="chunk-iade-1",
            text="İade süresi ürün tesliminden itibaren 14 gündür. Kargo ücretsizdir.",
            embedding_text="İade süresi ürün tesliminden itibaren 14 gündür. Kargo ücretsizdir.",
            source_file="iade.pdf",
            page_start=2,
            page_end=3,
            char_start=0,
            char_end=67,
            chunk_index=0,
            strategy=ChunkStrategy.STRUCTURE,
            token_count=12,
            heading_path=["İade Politikası", "Süre"],
        ),
    ]


@pytest.fixture
def memory_store(fake_embedder: FakeEmbedder, sample_chunks: list[Chunk]) -> QdrantStore:
    """Bellek içi (:memory:) QdrantStore ve hazır indekslenmiş veri."""
    client = QdrantClient(":memory:")
    config = QdrantConfig(
        url="http://localhost:6333",
        collection_prefix="test_answer_api",
    )
    store = QdrantStore(client=client, config=config, embedder=fake_embedder)
    store.ensure_collection()

    dense_vecs = fake_embedder.embed_documents([c.embedding_text for c in sample_chunks])
    store.upsert_chunks(sample_chunks, dense_vecs, doc_hash="hash_v1")
    return store


@pytest.fixture
def rag_service(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    fake_llm: FakeLLMProvider,
) -> RagAnswerService:
    """Bellek içi store ve sahte LLM ile yapılandırılmış RagAnswerService."""
    config = GenerationConfig(
        context_token_budget=500,
        top_k=3,
        min_dense_score=None,
        max_attempts=2,
        abstain_message="Aradığınız bilgi dokümanlarımızda bulunamadı.",
    )
    return RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=TiktokenTokenizer(),
        config=config,
    )


@pytest.fixture
def client(rag_service: RagAnswerService, memory_store: QdrantStore, fake_embedder: FakeEmbedder):
    """FastAPI TestClient; bağımlılıklar override edilir."""
    app.dependency_overrides[get_rag_answer_service] = lambda: rag_service
    app.dependency_overrides[get_qdrant_store] = lambda: memory_store
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ============================================================================
# BİRİM TESTLERİ (DOCKER / AĞ GEREKTİRMEZ)
# ============================================================================


def test_answer_happy_path(client: TestClient):
    """Başarılı cevap üretildiğinde 200 döner ve atıf detayları eksiksiz eşleşir."""
    response = client.post(
        "/rag/answer",
        json={"question": "İade süresi kaç gündür?", "k": 3},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "answered"
    assert "İade süresi 14 gündür [1]." in data["answer"]
    assert data["abstain_reason"] is None
    assert len(data["citations"]) == 1

    citation = data["citations"][0]
    assert citation["number"] == 1
    assert citation["chunk_id"] == "chunk-iade-1"
    assert citation["source_file"] == "iade.pdf"
    assert citation["page_start"] == 2
    assert citation["page_end"] == 3
    assert citation["heading_path"] == ["İade Politikası", "Süre"]


def test_answer_model_abstained(
    client: TestClient,
    fake_llm: FakeLLMProvider,
    rag_service: RagAnswerService,
):
    """LLM BULUNAMADI döndüğünde kurumsal abstain mesajı ve model_abstained kodu döner."""
    fake_llm.responses = ["BULUNAMADI"]
    fake_llm._has_responses = True

    response = client.post(
        "/rag/answer",
        json={"question": "Hangi kargo firmasıyla çalışıyorsunuz?"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "abstained"
    assert data["abstain_reason"] == "model_abstained"
    assert data["answer"] == rag_service.config.abstain_message
    assert data["citations"] == []


def test_answer_payload_isolation(client: TestClient):
    """Yanıtta dahili teşhis alanları (validation_issues, usage, top_dense_score vb.) sızmamalıdır."""
    response = client.post(
        "/rag/answer",
        json={"question": "İade süresi nedir?"},
    )

    assert response.status_code == 200
    data = response.json()

    # Yalnızca beklenen genel alanlar yer almalıdır
    allowed_keys = {"status", "answer", "abstain_reason", "citations"}
    assert set(data.keys()) == allowed_keys

    # Dahili hassas alanlar kesinlikle olmamalı
    assert "validation_issues" not in data
    assert "usage" not in data
    assert "top_dense_score" not in data
    assert "attempts" not in data
    assert "correlation_id" not in data


@pytest.mark.parametrize(
    "invalid_question",
    [
        "",  # Boş metin
        "   ",  # Yalnızca boşluk
        "\t\n  ",  # Boşluk ve yeni satır
    ],
)
def test_answer_empty_question_validation(client: TestClient, invalid_question: str):
    """Boş veya salt boşluk sorularda 422 Unprocessable Entity dönmelidir."""
    response = client.post(
        "/rag/answer",
        json={"question": invalid_question},
    )

    assert response.status_code == 422
    data = response.json()
    assert data.get("title") == "Doğrulama Hatası" or "detail" in data


def test_answer_question_too_long(client: TestClient):
    """1000 karakterden uzun sorularda 422 dönmelidir."""
    long_question = "a" * 1001
    response = client.post(
        "/rag/answer",
        json={"question": long_question},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("invalid_k", [0, 11, -1])
def test_answer_invalid_k_validation(client: TestClient, invalid_k: int):
    """k parametresi 1..10 aralığı dışında ise 422 dönmelidir."""
    response = client.post(
        "/rag/answer",
        json={"question": "İade süresi?", "k": invalid_k},
    )

    assert response.status_code == 422


def test_answer_service_not_configured():
    """rag_answer_service FastAPI app.state üzerinde yoksa 503 dönmelidir."""
    app.dependency_overrides.clear()
    with TestClient(app) as raw_client:
        # app.state.rag_answer_service'in None olmasını garanti edelim
        old_service = getattr(app.state, "rag_answer_service", None)
        app.state.rag_answer_service = None
        try:
            response = raw_client.post(
                "/rag/answer",
                json={"question": "İade süresi?"},
            )
            assert response.status_code == 503
            assert "yapılandırılmamış" in response.json()["detail"]
        finally:
            app.state.rag_answer_service = old_service


def test_answer_unindexed_collection_returns_503(
    client: TestClient,
    rag_service: RagAnswerService,
):
    """Koleksiyon henüz indekslenmemişse 503 dönmeli ve açıklayıcı mesaj içermelidir."""
    # Koleksiyonu silerek simüle edelim
    rag_service.store.client.delete_collection(rag_service.store.collection_name)

    response = client.post(
        "/rag/answer",
        json={"question": "İade süresi?"},
    )

    assert response.status_code == 503
    data = response.json()
    assert "henüz indekslenmemiş" in data["detail"]


def test_answer_timeout_returns_503_without_leak(
    client: TestClient,
    fake_llm: FakeLLMProvider,
):
    """TimeoutError durumunda 503 dönmeli ve iç stack trace sızdırılmamalıdır."""
    fake_llm.raise_on_call = TimeoutError("Internal socket timeout")

    response = client.post(
        "/rag/answer",
        json={"question": "İade süresi?"},
    )

    assert response.status_code == 503
    data = response.json()
    assert "zaman aşımına" in data["detail"]
    assert "Internal socket timeout" not in str(data)


def test_answer_unexpected_error_returns_503_without_leak(
    client: TestClient,
    fake_llm: FakeLLMProvider,
):
    """Beklenmeyen RuntimeError durumunda gizli mesaj sızdırılmadan 503 dönmelidir."""
    fake_llm.raise_on_call = RuntimeError("DATABASE_PASSWORD_LEAK_SECRET_123")

    response = client.post(
        "/rag/answer",
        json={"question": "İade süresi?"},
    )

    assert response.status_code == 503
    data = response.json()
    assert "DATABASE_PASSWORD_LEAK_SECRET_123" not in str(data)
    assert data["detail"] == "Cevap üretilirken bir hata oluştu."


def test_answer_turn_timeout_returns_503(client: TestClient, runtime_override):
    """RAG_TURN_TIMEOUT_SEC aşıldığında 503 ve zaman aşımı mesajı dönmelidir."""
    import asyncio
    from app.api.answer import get_rag_answer_service
    from app.rag.generation.models import GenerationConfig

    class SlowRagService:
        config = GenerationConfig()

        async def answer(self, *args, **kwargs):
            await asyncio.sleep(0.5)
            raise RuntimeError("Should not be reached")

    app.dependency_overrides[get_rag_answer_service] = lambda: SlowRagService()
    runtime_override(rag={"turn_timeout_sec": 0.05, "llm_timeout_sec": 0.05})
    try:
        response = client.post(
            "/rag/answer",
            json={"question": "İade süresi?"},
        )
        assert response.status_code == 503
        assert "zaman aşımına" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_rag_answer_service, None)


def test_answer_overloaded_returns_503(client: TestClient):
    """ConcurrencyLimiter slotu doluyken /rag/answer 503 Overloaded dönmelidir."""
    from app.core.limits import ConcurrencyLimiter

    old_limiter = getattr(app.state, "ai_limiter", None)
    app.state.ai_limiter = ConcurrencyLimiter(max_concurrent=1)
    app.state.ai_limiter._current_count = 1
    try:
        response = client.post(
            "/rag/answer",
            json={"question": "İade süresi?"},
        )
        assert response.status_code == 503
        data = response.json()
        assert data["type"] == "https://api.commerce.com/errors/ai-overloaded"
        assert data["retryable"] is True
        assert data["retry_after_seconds"] == 5
        assert response.headers.get("Retry-After") == "5"
    finally:
        app.state.ai_limiter = old_limiter


def test_answer_token_budget_exceeded_returns_429(client: TestClient, runtime_override):
    """RAG cevabında bütçe aşıldığında 429 TokenBudgetExceeded dönmelidir."""
    from app.budget.service import TokenBudgetService
    from app.budget.store import InMemoryBudgetStore

    store = InMemoryBudgetStore()
    svc = TokenBudgetService(
        store=store,
        daily_limit=5,
        per_minute_limit=5,
    )
    app.state.token_budget = svc
    runtime_override(budget={"daily_limit": 5, "per_minute_limit": 5})
    try:
        response = client.post(
            "/rag/answer",
            json={"question": "İade süresi kaç gündür?"},
        )
        assert response.status_code == 429
        data = response.json()
        assert data["type"] == "https://api.commerce.com/errors/token-budget-exceeded"
        assert data["retryable"] is True
        assert data["retry_after_seconds"] > 0
        assert response.headers.get("Retry-After") is not None
    finally:
        app.state.token_budget = None


def test_answer_passes_runtime_config_to_generation_service(client: TestClient, runtime_override):
    """Runtime snapshot içindeki rag ayarları nesil servisine aktarılır."""
    captured_configs = []

    class SpyAnswerService:
        config = GenerationConfig()
        tokenizer = TiktokenTokenizer()

        async def answer(self, question, *, k=None, config=None, **kwargs):
            captured_configs.append(config)
            from app.rag.generation.models import RagAnswer
            return RagAnswer(
                status="answered",
                answer="Test cevabı",
                citations=[],
            )

    runtime_override(rag={"top_k": 3, "temperature": 0.3})
    app.dependency_overrides[get_rag_answer_service] = lambda: SpyAnswerService()

    try:
        response = client.post(
            "/rag/answer",
            json={"question": "Kargo kaç günde gelir?"},
        )
        assert response.status_code == 200
        assert len(captured_configs) == 1
        assert captured_configs[0] is not None
        assert captured_configs[0].top_k == 3
        assert captured_configs[0].temperature == 0.3
    finally:
        app.dependency_overrides.pop(get_rag_answer_service, None)


