"""search.py ve retriever.py için birim testleri."""

import pytest
from qdrant_client import QdrantClient

from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.chunking.tokenizer import WhitespaceTokenizer
from app.rag.embedding.fake import FakeEmbedder
from app.rag.evaluation.chunking.retrieval import Retriever
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.retriever import QdrantRetriever
from app.rag.vectorstore.search import (
    SearchFilter,
    search_dense,
    search_hybrid,
    search_sparse,
)
from app.rag.vectorstore.store import QdrantStore


def _make_chunk(cid: str, source_file: str, text: str, page: int = 1) -> Chunk:
    """Testler için geçerli bir Chunk nesnesi üretir."""
    return Chunk(
        id=cid,
        strategy=ChunkStrategy.STRUCTURE,
        source_file=source_file,
        chunk_index=0,
        text=text,
        page_start=page,
        page_end=page,
        char_start=0,
        char_end=len(text),
        token_count=len(text.split()),
    )


@pytest.fixture
def search_fixture():
    """3 adet özel kurgulanmış chunk ile hazırlanmış bellek içi test ortamı."""
    client = QdrantClient(":memory:")
    config = QdrantConfig(collection_prefix="test_search", upsert_batch_size=10)
    embedder = FakeEmbedder(dimensions=64, model_id="fake/test-model")
    store = QdrantStore(client=client, config=config, embedder=embedder)
    store.ensure_collection()
    store.ensure_payload_indexes()

    chunks = [
        # Chunk 1: Elektronik odaklı
        _make_chunk(
            cid="chk_elektronik",
            source_file="elektronik.pdf",
            text="Elektronik ürünlerde iade politikası ve genel kurallar. Müşteri memnuniyeti esastır.",
            page=1,
        ),
        # Chunk 2: Giyim odaklı
        _make_chunk(
            cid="chk_giyim",
            source_file="giyim.pdf",
            text="Giyim ve tekstil ürünlerinde iade politikası ve genel kurallar. Hijyen bantları açılmamalıdır.",
            page=2,
        ),
        # Chunk 3: Nadir anahtar kelimeli yazılım lisansı
        _make_chunk(
            cid="chk_yazilim",
            source_file="yazilim.pdf",
            text="Özel istisna: Kripto cüzdanı ve yazılım lisanslarında kesinlikle iade yoktur. Model TX999.",
            page=3,
        ),
    ]

    # Store'a kaydet
    dense_vecs = embedder.embed_documents([c.embedding_text for c in chunks])
    store.upsert_chunks(chunks, dense_vecs, doc_hash="fixture_hash")

    return store, embedder, chunks


def test_retriever_protocol_compliance(search_fixture):
    """QdrantRetriever sınıfı projede tanımlı Retriever protokolüne tam uymalıdır."""
    store, embedder, _ = search_fixture
    retriever = QdrantRetriever(store=store, embedder=embedder, mode="hybrid")
    assert isinstance(retriever, Retriever)


def test_dense_search_ranks_semantic_overlap_first(search_fixture):
    """Dense arama, sorguyla en çok anlamsal/kelime örtüşmesi olan chunk'ı 1. sıraya getirmelidir."""
    store, embedder, chunks = search_fixture
    query = "Elektronik ürünlerde müşteri memnuniyeti"
    q_vec = embedder.embed_query(query)

    hits = search_dense(store.client, store.collection_name, q_vec, k=3)
    assert len(hits) == 3
    assert hits[0].chunk.id == "chk_elektronik"
    assert hits[0].source == "dense"


def test_sparse_search_ranks_rare_keyword_first(search_fixture):
    """Sparse arama, yalnızca bir dokümanda geçen nadir anahtar kelimeyi (TX999) 1. sıraya getirmelidir."""
    store, _, _ = search_fixture
    query = "Model TX999 kripto lisansı"
    q_sparse = store.sparse_encoder.encode_query(query)

    hits = search_sparse(store.client, store.collection_name, q_sparse, k=3)
    assert len(hits) > 0
    assert hits[0].chunk.id == "chk_yazilim"
    assert hits[0].source == "sparse"


def test_hybrid_search_ranks_both_first(search_fixture):
    """Hem dense hem sparse'ta yüksek olan doküman hybrid aramada birinci olmalıdır."""
    store, embedder, _ = search_fixture
    query = "Elektronik ürünlerde iade politikası"
    q_vec = embedder.embed_query(query)
    q_sparse = store.sparse_encoder.encode_query(query)

    hits = search_hybrid(store.client, store.collection_name, q_vec, q_sparse, k=3)
    assert len(hits) == 3
    assert hits[0].chunk.id == "chk_elektronik"
    assert hits[0].source == "hybrid"


def test_source_file_filter_isolates_document(search_fixture):
    """source_file filtresi verildiğinde yalnızca hedef dosyaya ait chunk'lar dönmelidir."""
    store, embedder, _ = search_fixture
    # Sorgu genel bir iade sorgusu ama sadece giyim.pdf istiyoruz
    retriever = QdrantRetriever(
        store=store,
        embedder=embedder,
        mode="hybrid",
        filter=SearchFilter(source_file="giyim.pdf"),
    )

    results = retriever.search("iade politikası ve kurallar", k=5)
    assert len(results) == 1
    assert results[0].id == "chk_giyim"
    assert results[0].source_file == "giyim.pdf"


def test_page_range_filter(search_fixture):
    """Sayfa filtresi aralıktaki chunk'ları getirmelidir."""
    store, embedder, _ = search_fixture
    retriever = QdrantRetriever(
        store=store,
        embedder=embedder,
        mode="dense",
        filter=SearchFilter(page_start=2, page_end=3),
    )

    results = retriever.search("ürün iade", k=5)
    # 2. ve 3. sayfalardaki chunk'lar dönmeli, 1. sayfadaki elektronik dönmemeli
    returned_pages = {c.page_start for c in results}
    assert 1 not in returned_pages
    assert returned_pages.issubset({2, 3})


def test_page_single_boundary_filters(search_fixture):
    """Yalnızca page_start veya yalnızca page_end verildiğinde filtre doğru çalışmalıdır."""
    store, embedder, _ = search_fixture

    # Sadece page_start >= 3
    retriever_start = QdrantRetriever(
        store=store,
        embedder=embedder,
        mode="dense",
        filter=SearchFilter(page_start=3),
    )
    res_start = retriever_start.search("iade", k=5)
    assert len(res_start) == 1
    assert res_start[0].page_start == 3

    # Sadece page_end <= 2
    retriever_end = QdrantRetriever(
        store=store,
        embedder=embedder,
        mode="dense",
        filter=SearchFilter(page_end=2),
    )
    res_end = retriever_end.search("iade", k=5)
    for c in res_end:
        assert c.page_end <= 2



def test_search_by_budget_respects_limit(search_fixture):
    """search_by_budget bütçeyi kesinlikle aşmamalıdır."""
    store, embedder, _ = search_fixture
    retriever = QdrantRetriever(store=store, embedder=embedder, mode="hybrid")
    tokenizer = WhitespaceTokenizer()

    # Çok küçük bütçe (en az 1 chunk döner ama 2. chunk'ı eklemez)
    budget = 15
    selected = retriever.search_by_budget("iade politikası", budget=budget, tokenizer=tokenizer)
    assert len(selected) >= 1
    total_tokens = sum(tokenizer.count(c.text) for c in selected)
    # İlk chunk bütçeyi tek başına aşsa bile döner, sonrakiler bütçeyi aşamaz
    if len(selected) > 1:
        assert total_tokens <= budget


def test_search_by_budget_caps_candidates_at_50(search_fixture, monkeypatch):
    """search_by_budget koleksiyonda binlerce point olsa bile en fazla 50 aday çekmelidir."""
    store, embedder, _ = search_fixture
    retriever = QdrantRetriever(store=store, embedder=embedder, mode="hybrid")
    tokenizer = WhitespaceTokenizer()

    # store.count()'un 10,000 döndüğünü simüle et
    monkeypatch.setattr(store, "count", lambda *args, **kwargs: 10_000)

    searched_k = []
    original_search = retriever.search

    def spy_search(query: str, k: int = 5):
        searched_k.append(k)
        return original_search(query, k=k)

    monkeypatch.setattr(retriever, "search", spy_search)

    retriever.search_by_budget("iade", budget=100, tokenizer=tokenizer)
    assert len(searched_k) == 1
    assert searched_k[0] == 50  # 10,000 değil kesinlikle 50 ile sınırlandırılmış olmalı



def test_empty_query_returns_empty(search_fixture):
    """Boş sorgu veya k=0 durumlarında boş liste dönmelidir."""
    store, embedder, _ = search_fixture
    retriever = QdrantRetriever(store=store, embedder=embedder, mode="hybrid")
    tokenizer = WhitespaceTokenizer()

    assert retriever.search("") == []
    assert retriever.search("   ") == []
    assert retriever.search("iade", k=0) == []
    assert retriever.search_by_budget("", budget=100, tokenizer=tokenizer) == []
    assert retriever.search_by_budget("iade", budget=0, tokenizer=tokenizer) == []
