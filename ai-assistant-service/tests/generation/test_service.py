import pytest
from qdrant_client import QdrantClient

from app.llm.base import ChatMessage
from app.llm.fake import FakeLLMProvider
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.embedding.fake import FakeEmbedder
from app.rag.generation.models import GenerationConfig
from app.rag.generation.service import RagAnswerService
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
        collection_prefix="test_generation_service",
    )
    store = QdrantStore(client=client, config=config, embedder=fake_embedder)
    store.ensure_collection()

    chunks = _create_sample_chunks()
    dense_vecs = fake_embedder.embed_documents([c.text for c in chunks])
    store.upsert_chunks(chunks, dense_vecs, doc_hash="v1")
    return store


@pytest.fixture
def generation_config() -> GenerationConfig:
    return GenerationConfig(
        top_k=3,
        context_token_budget=1500,
        min_dense_score=None,
        max_attempts=2,
        temperature=0.0,
        max_output_tokens=400,
        llm_timeout_sec=30.0,
        abstain_message="Dokümanlarda bu bilgi bulunamadı.",
        retrieval_mode="dense",
    )


@pytest.mark.anyio
async def test_service_happy_path(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
) -> None:
    fake_llm = FakeLLMProvider(responses=["İade süresi 14 gündür [1]."])
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    result = await service.answer("İade süresi kaç gün?")

    assert result.status == "answered"
    assert result.abstain_reason is None
    assert result.attempts == 1
    assert result.answer == "İade süresi 14 gündür [1]."
    assert len(result.citations) == 1
    assert result.citations[0].number == 1
    assert result.citations[0].chunk_id == "chunk-1"
    assert result.citations[0].source_file == "iade.pdf"
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0


@pytest.mark.anyio
async def test_service_model_abstained(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
) -> None:
    fake_llm = FakeLLMProvider(responses=["BULUNAMADI"])
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    result = await service.answer("Bilinmeyen bir konu?")

    assert result.status == "abstained"
    assert result.abstain_reason == "model_abstained"
    assert result.attempts == 1
    assert result.answer == generation_config.abstain_message
    assert result.citations == []


@pytest.mark.anyio
async def test_service_retry_succeeds(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
) -> None:
    # 1. yanıt atıfsız (hata), 2. yanıt doğru atıflı
    fake_llm = FakeLLMProvider(
        responses=[
            "İade süresi 14 gündür.",
            "İade süresi 14 gündür [1].",
        ]
    )
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    result = await service.answer("İade süresi nedir?")

    assert result.status == "answered"
    assert result.attempts == 2
    assert len(fake_llm.calls) == 2
    # 2. çağrının mesajlarında hata detayı olmalı
    retry_user_msg = fake_llm.calls[1]["messages"][-1].content
    assert "kaynak numarası belirtilmemiş" in retry_user_msg


@pytest.mark.anyio
async def test_service_retry_fails_abstains_with_validation_failed(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
) -> None:
    # İki çağrıda da atıf yok
    fake_llm = FakeLLMProvider(
        responses=[
            "Cevap bir.",
            "Cevap iki.",
        ]
    )
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    result = await service.answer("Soru?")

    assert result.status == "abstained"
    assert result.abstain_reason == "validation_failed"
    assert result.attempts == 2
    assert result.answer == generation_config.abstain_message
    assert len(result.validation_issues) > 0


@pytest.mark.anyio
async def test_service_empty_collection_abstains_no_results(
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
) -> None:
    client = QdrantClient(":memory:")
    config = QdrantConfig(collection_prefix="empty_coll")
    empty_store = QdrantStore(client=client, config=config, embedder=fake_embedder)
    empty_store.ensure_collection()

    fake_llm = FakeLLMProvider(responses=["Asla çağrılmamalı"])
    service = RagAnswerService(
        store=empty_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    result = await service.answer("Herhangi bir soru")

    assert result.status == "abstained"
    assert result.abstain_reason == "no_results"
    assert result.attempts == 0
    assert len(fake_llm.calls) == 0


@pytest.mark.anyio
async def test_service_gate_low_dense_score_abstains(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
) -> None:
    # Cosine skoru 1.01'den büyük olamaz; kapı kesinlikle tetiklenmeli
    cfg = GenerationConfig(
        min_dense_score=1.01,
        abstain_message="Bulunamadı.",
        retrieval_mode="dense",
    )
    fake_llm = FakeLLMProvider(responses=["Asla çağrılmamalı"])
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=cfg,
    )

    result = await service.answer("İade süresi?")

    assert result.status == "abstained"
    assert result.abstain_reason == "low_retrieval_score"
    assert result.attempts == 0
    assert len(fake_llm.calls) == 0


@pytest.mark.anyio
async def test_service_gate_closed_does_not_call_extra_dense_search(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # min_dense_score None iken ek search_dense çağrılmamalı
    generation_config = generation_config.model_copy(update={"min_dense_score": None, "retrieval_mode": "hybrid"})
    dense_call_count = 0

    import app.rag.generation.service as service_module
    orig_search_dense = service_module.search_dense

    def counted_search_dense(*args, **kwargs):
        nonlocal dense_call_count
        dense_call_count += 1
        return orig_search_dense(*args, **kwargs)

    monkeypatch.setattr(service_module, "search_dense", counted_search_dense)

    fake_llm = FakeLLMProvider(responses=["14 gündür [1]."])
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    result = await service.answer("İade?")
    assert result.status == "answered"
    assert dense_call_count == 0  # hybrid modunda ek dense çağrısı 0 olmalı!


@pytest.mark.anyio
async def test_service_pii_masked_in_llm_and_embedder(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_llm = FakeLLMProvider(responses=["14 gündür [1]."])
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    seen_queries: list[str] = []
    orig_embed = fake_embedder.embed_query

    def spied_embed(q: str):
        seen_queries.append(q)
        return orig_embed(q)

    monkeypatch.setattr(fake_embedder, "embed_query", spied_embed)

    valid_tckn = "54321098710"
    question = f"Benim TCKN numaram {valid_tckn}, iade süresi kaç gün?"

    result = await service.answer(question, source_file="iade.pdf")
    assert result.status == "answered"

    # LLM mesajlarını kontrol et: Gerçek TCKN asla olmamalı, [TCKN] olmalı
    sent_prompt = fake_llm.calls[0]["messages"][-1].content
    assert valid_tckn not in sent_prompt
    assert "[TCKN]" in sent_prompt

    # Embedder'ın aldığı metinleri kontrol et
    assert len(seen_queries) == 1
    assert valid_tckn not in seen_queries[0]
    assert "[TCKN]" in seen_queries[0]


@pytest.mark.anyio
async def test_service_llm_timeout_raises(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
) -> None:
    # 0.1 sn gecikmeli LLM, 0.02 sn timeout
    fast_timeout_cfg = generation_config.model_copy(update={"llm_timeout_sec": 0.02})
    delayed_llm = FakeLLMProvider(responses=["Geç"], delay_sec=0.1)
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=delayed_llm,
        tokenizer=WhitespaceTokenizer(),
        config=fast_timeout_cfg,
    )

    with pytest.raises(TimeoutError):
        await service.answer("Soru?")


@pytest.mark.anyio
async def test_service_budget_truncation_catches_invalid_citation(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
) -> None:
    # Çok dar bütçe -> Sadece 1 blok sığar
    tight_cfg = generation_config.model_copy(update={"context_token_budget": 20, "max_attempts": 1})
    # Model 2. kaynağa atıf yapıyor ama dar bütçede sadece 1 kaynak var!
    fake_llm = FakeLLMProvider(responses=["Kargo ücretsizdir [2]."])
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=tight_cfg,
    )

    result = await service.answer("Kargo?")
    assert result.status == "abstained"
    assert result.abstain_reason == "validation_failed"
    assert any(i.type == "invalid_citation" for i in result.validation_issues)


@pytest.mark.anyio
async def test_service_citations_only_includes_actually_used_numbers(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
) -> None:
    # 3 blok context'e girer, model sadece 2. bloğa atıf yapar
    fake_llm = FakeLLMProvider(responses=["Kargo bedavadır [2]."])
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    result = await service.answer("Kargo ücreti?")
    assert result.status == "answered"
    assert len(result.citations) == 1
    assert result.citations[0].number == 2
    assert result.citations[0].chunk_id == "chunk-2"


@pytest.mark.anyio
async def test_service_usage_aggregated_across_attempts(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
) -> None:
    # 2 deneme yapılacak
    fake_llm = FakeLLMProvider(
        responses=[
            "Hata bir iki.",
            "İade süresi 14 gündür [1].",
        ]
    )
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    result = await service.answer("İade?")
    assert result.status == "answered"
    assert result.attempts == 2

    # İki çağrının kelime sayıları toplanmış olmalı
    call1_in = sum(len(m.content.split()) for m in fake_llm.calls[0]["messages"])
    call1_out = len("Hata bir iki.".split())

    call2_in = sum(len(m.content.split()) for m in fake_llm.calls[1]["messages"])
    call2_out = len("İade süresi 14 gündür [1].".split())

    assert result.usage.input_tokens == call1_in + call2_in
    assert result.usage.output_tokens == call1_out + call2_out


@pytest.mark.anyio
async def test_service_logs_on_exception(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """İstisna (timeout, LLM hatası) durumunda da her durumda yapılandırılmış log yazılmalıdır."""
    import logging

    fake_llm = FakeLLMProvider(raise_on_call=TimeoutError("LLM call timed out"))
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(TimeoutError):
            await service.answer("İade süresi?", correlation_id="test-corr-fail")

    # Loglarda hata satırı bulunmalı ve soru metni sızmamalı
    assert any("RAG Answer Generation failed with error" in r.message for r in caplog.records)
    assert any("test-corr-fail" in r.message for r in caplog.records)
    assert not any("İade süresi?" in r.message for r in caplog.records)


@pytest.mark.anyio
async def test_service_respects_per_call_generation_config(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    generation_config: GenerationConfig,
) -> None:
    """RagAnswerService dinamik config ile çağrıldığında o ayarları kullanır."""
    fake_llm = FakeLLMProvider(responses=["İade süresi 14 gündür [1].", "İkinci cevap [1]."])
    service = RagAnswerService(
        store=memory_store,
        embedder=fake_embedder,
        llm=fake_llm,
        tokenizer=WhitespaceTokenizer(),
        config=generation_config,
    )

    # 1. config=None -> self.config kullanılır
    outcome1 = service.retrieve_with_rerank("İade süresi?", k=generation_config.top_k, config=None)
    assert len(outcome1.hits) == generation_config.top_k

    # 2. Özel GenerationConfig(top_k=1, temperature=0.2) ile çağrı
    custom_cfg = generation_config.model_copy(update={"top_k": 1, "temperature": 0.2})
    outcome2 = service.retrieve_with_rerank("İade süresi?", k=1, config=custom_cfg)
    assert len(outcome2.hits) == 1

    # 3. answer() metoduna custom_cfg aktarımı
    ans = await service.answer("İade süresi?", config=custom_cfg)
    assert ans.status == "answered"
    assert fake_llm.calls[-1]["temperature"] == 0.2

