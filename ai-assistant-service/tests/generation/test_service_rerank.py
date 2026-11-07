import asyncio
import logging
import pytest
from qdrant_client import QdrantClient

from app.llm.fake import FakeLLMProvider
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.embedding.fake import FakeEmbedder
from app.rag.generation.models import GenerationConfig
from app.rag.generation.service import RagAnswerService
from app.rag.rerank.fake import FakeReranker
from app.rag.rerank.models import RerankError
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.store import QdrantStore


def _create_sample_chunks() -> list[Chunk]:
    return [
        Chunk(
            id="chunk-1",
            text="İade süresi ürün tesliminden itibaren 14 gündür.",
            source_file="iade.pdf",
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=48,
            chunk_index=0,
            strategy=ChunkStrategy.STRUCTURE,
            token_count=7,
            heading_path=["İade", "Süre"],
        ),
        Chunk(
            id="chunk-2",
            text="Sipariş tutarı 1.000 TL üzeri olan alışverişlerde kargo bedavadır.",
            source_file="kargo.pdf",
            page_start=1,
            page_end=2,
            char_start=0,
            char_end=66,
            chunk_index=0,
            strategy=ChunkStrategy.STRUCTURE,
            token_count=9,
            heading_path=["Kargo", "Ücretler"],
        ),
        Chunk(
            id="chunk-3",
            text="Hijyen bandı açılmış olan kozmetik ürünlerinde iade kabul edilmez.",
            source_file="istisnalar.pdf",
            page_start=3,
            page_end=3,
            char_start=0,
            char_end=66,
            chunk_index=0,
            strategy=ChunkStrategy.STRUCTURE,
            token_count=9,
            heading_path=["İade", "İstisnalar"],
        ),
    ]


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder(dimensions=16)


@pytest.fixture
def memory_store(fake_embedder: FakeEmbedder) -> QdrantStore:
    client = QdrantClient(":memory:")
    config = QdrantConfig(
        url="http://localhost:6333",
        collection_prefix="test_service_rerank",
    )
    store = QdrantStore(client=client, config=config, embedder=fake_embedder)
    store.ensure_collection()

    chunks = _create_sample_chunks()
    dense_vecs = fake_embedder.embed_documents([c.text for c in chunks])
    store.upsert_chunks(chunks, dense_vecs, doc_hash="v1")
    return store


@pytest.mark.anyio
async def test_service_rerank_disabled_by_default(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
) -> None:
    fake_llm = FakeLLMProvider(responses=["İade süresi 14 gündür [1]."])
    fake_reranker = FakeReranker(scores=[0.1, 0.9, 0.5])
    config = GenerationConfig(top_k=2, rerank_enabled=False)

    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=config,
        reranker=fake_reranker,
    )

    result = await service.answer("İade süresi kaç gün?")
    assert result.status == "answered"
    assert result.rerank_status == "disabled"
    assert len(fake_reranker.calls) == 0


@pytest.mark.anyio
async def test_service_rerank_enabled_reorders_context(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
) -> None:
    # Arama 'Kargo' sorgusuyla chunk-2'yi ilk sıraya getirir [chunk-2, chunk-1, chunk-3]
    # Reranker scores=[0.1, 0.95, 0.5] ile chunk-1'i (index 1) ilk sıraya taşır
    fake_llm = FakeLLMProvider(responses=["İade süresi 14 gündür [1]."])
    fake_reranker = FakeReranker(scores=[0.1, 0.95, 0.5])
    config = GenerationConfig(top_k=2, rerank_enabled=True, rerank_candidates=10)

    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=config,
        reranker=fake_reranker,
    )

    result = await service.answer("Kargo ücreti ne kadar?")
    assert result.status == "answered"
    assert result.rerank_status == "ok"
    assert len(fake_reranker.calls) == 1
    # Yeniden sıralama sonucu chunk-1 [1] numaralı blok oldu, chunk-2 ilk 2'den elendi
    assert result.context_chunk_ids[0] == "chunk-1"
    assert "chunk-2" not in result.context_chunk_ids
    assert len(result.context_chunk_ids) == 2


@pytest.mark.anyio
async def test_service_rerank_fail_open(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
) -> None:
    fake_llm = FakeLLMProvider(responses=["İade süresi 14 gündür [1]."])
    broken_reranker = FakeReranker(raise_on_call=RerankError("Cohere zaman aşımı"))
    config = GenerationConfig(top_k=2, rerank_enabled=True, rerank_fail_open=True)

    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=config,
        reranker=broken_reranker,
    )

    result = await service.answer("İade süresi kaç gün?")
    # Fail-open: sistem durmaz, cevap üretilir, rerank_status="failed"
    assert result.status == "answered"
    assert result.rerank_status == "failed"


@pytest.mark.anyio
async def test_service_rerank_fail_closed(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
) -> None:
    fake_llm = FakeLLMProvider(responses=["cevap"])
    broken_reranker = FakeReranker(raise_on_call=RerankError("Reranker çöktü"))
    config = GenerationConfig(top_k=2, rerank_enabled=True, rerank_fail_open=False)

    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=config,
        reranker=broken_reranker,
    )

    with pytest.raises(RerankError, match="Reranker çöktü"):
        await service.answer("İade süresi kaç gün?")


@pytest.mark.anyio
async def test_service_rerank_gate_unaffected(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
) -> None:
    fake_llm = FakeLLMProvider(responses=["cevap"])
    fake_reranker = FakeReranker(scores=[0.99, 0.99, 0.99])
    # Kapı eşiği çok yüksek tutulursa rerank açık olsa bile abstain edilir
    config = GenerationConfig(top_k=2, min_dense_score=1.5, rerank_enabled=True)

    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=config,
        reranker=fake_reranker,
    )

    result = await service.answer("İade süresi kaç gün?")
    assert result.status == "abstained"
    assert result.abstain_reason == "low_retrieval_score"
    # Reranker çağrılmış ve durumu iletilmiş olmalı
    assert result.rerank_status == "ok"


@pytest.mark.anyio
async def test_service_rerank_pii_masked(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
) -> None:
    fake_llm = FakeLLMProvider(responses=["BULUNAMADI"])
    fake_reranker = FakeReranker(scores=[0.9, 0.1, 0.1])
    config = GenerationConfig(top_k=2, rerank_enabled=True)

    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=config,
        reranker=fake_reranker,
    )

    # 54321098710 geçerli bir TCKN checksum'ına sahiptir
    await service.answer("Benim TCKN 54321098710, iade süresi nedir?")
    assert len(fake_reranker.calls) == 1
    # Reranker'a giden soru maskelenmiş olmalıdır
    rerank_query = fake_reranker.calls[0]["query"]
    assert "54321098710" not in rerank_query
    assert "[TCKN]" in rerank_query


@pytest.mark.anyio
async def test_service_rerank_concurrent_calls(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
) -> None:
    fake_llm = FakeLLMProvider(responder=lambda msgs: "BULUNAMADI")
    fake_reranker = FakeReranker(scores=[0.8, 0.5, 0.1])
    config = GenerationConfig(top_k=2, rerank_enabled=True)

    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=config,
        reranker=fake_reranker,
    )

    tasks = [service.answer(f"Soru {i}?") for i in range(10)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 10
    for res in results:
        assert res.rerank_status == "ok"
        assert res.status == "abstained"


@pytest.mark.anyio
async def test_service_rerank_logging_fields(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_llm = FakeLLMProvider(responses=["İade süresi 14 gündür [1]."])
    fake_reranker = FakeReranker(scores=[0.9, 0.5, 0.1])
    config = GenerationConfig(top_k=2, rerank_enabled=True)

    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=config,
        reranker=fake_reranker,
    )

    with caplog.at_level(logging.INFO):
        await service.answer("Gizli soru metni 999")

    log_text = caplog.text
    assert "'rerank_status': 'ok'" in log_text
    assert "'latency_rerank_ms':" in log_text
    assert "Gizli soru metni 999" not in log_text


def test_service_rerank_enabled_without_reranker_instance(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = GenerationConfig(rerank_enabled=True)
    with caplog.at_level(logging.WARNING):
        service = RagAnswerService(
            store=memory_store,
            embedder=fake_embedder,
            llm=FakeLLMProvider(),
            tokenizer=WhitespaceTokenizer(),
            config=config,
            reranker=None,
        )

    assert "rerank_enabled=True olarak ayarlanmış ancak servise reranker örneği verilmemiş" in caplog.text
    outcome = service.retrieve_with_rerank("soru", k=2)
    assert outcome.rerank_status == "disabled"
