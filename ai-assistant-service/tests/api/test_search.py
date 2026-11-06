"""Search API birim ve entegrasyon testleri (POST /rag/search).

Test Edilen Durumlar:
1. Başarılı Arama (200 OK): Doğru chunk'ların ve skorların dönmesi.
2. Alan İzolasyonu: embedding_text veya char_start/end gibi dahili alanların yanıtta OLMAMASI.
3. Giriş Doğrulama (422 Unprocessable Entity):
   - Boş veya sadece boşluktan oluşan sorgular.
   - k = 0 ve k = 21 gibi sınır dışı değerler.
4. Kaynak Dosya Filtreleme (source_file): Yalnızca filtrelenen dosyanın chunk'larının dönmesi.
5. Koleksiyon Yokluğu (503 Service Unavailable): Henüz indekslenmemiş koleksiyon uyarısı.
6. Hata İzolasyonu (503 Service Unavailable): Veritabanı çöküşünde iç hata/URL sızdırılmaması.
7. Mod Desteği: dense, sparse ve hybrid modlarının sorunsuz çalışması.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.api.search import get_embedder, get_qdrant_store
from app.main import app
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.embedding.fake import FakeEmbedder
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.store import QdrantStore


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    """16 boyutlu deterministik sahte embedder."""
    return FakeEmbedder(dimensions=16)


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    """Test için örnek doküman parçaları."""
    return [
        Chunk(
            id="chunk-sozlesme-1",
            text="Mesafeli satış sözleşmesi genel koşulları ve alıcı hakları.",
            embedding_text="Mesafeli satış sözleşmesi genel koşulları ve alıcı hakları.",
            source_file="sozlesme.pdf",
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=59,
            chunk_index=0,
            strategy=ChunkStrategy.STRUCTURE,
            token_count=10,
            heading_path=["Sözleşme", "Genel"],
        ),
        Chunk(
            id="chunk-iade-1",
            text="İade süresi ürün tesliminden itibaren 14 gündür. Kargo ücretsizdir.",
            embedding_text="İade süresi ürün tesliminden itibaren 14 gündür. Kargo ücretsizdir.",
            source_file="iade.pdf",
            page_start=2,
            page_end=2,
            char_start=0,
            char_end=67,
            chunk_index=0,
            strategy=ChunkStrategy.STRUCTURE,
            token_count=10,
            heading_path=["İade Politikası", "Süre"],
        ),
    ]


@pytest.fixture
def memory_store(fake_embedder: FakeEmbedder, sample_chunks: list[Chunk]) -> QdrantStore:
    """Bellek içi (:memory:) QdrantStore ve hazır indekslenmiş veri."""
    client = QdrantClient(":memory:")
    config = QdrantConfig(
        url="http://localhost:6333",
        collection_prefix="test_search_api",
    )
    store = QdrantStore(client=client, config=config, embedder=fake_embedder)
    store.ensure_collection()

    dense_vecs = fake_embedder.embed_documents([c.embedding_text for c in sample_chunks])
    store.upsert_chunks(sample_chunks, dense_vecs, doc_hash="hash_v1")
    return store


@pytest.fixture
def client(memory_store: QdrantStore, fake_embedder: FakeEmbedder):
    """FastAPI TestClient; bağımlılıklar bellek içi store ile override edilir."""
    app.dependency_overrides[get_qdrant_store] = lambda: memory_store
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ============================================================================
# BİRİM TESTLERİ (DOCKER / AĞ GEREKTİRMEZ)
# ============================================================================


def test_search_valid_query_returns_200_and_expected_fields(client: TestClient):
    """Geçerli bir sorgu 200 döner ve yalnızca izin verilen DTO alanlarını içerir."""
    response = client.post(
        "/rag/search",
        json={"query": "iade süresi", "k": 2, "mode": "hybrid"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "hits" in data
    assert len(data["hits"]) > 0

    hit = data["hits"][0]
    # Beklenen genel alanlar
    assert "chunk_id" in hit
    assert "score" in hit
    assert "text" in hit
    assert "source_file" in hit
    assert "page_start" in hit
    assert "page_end" in hit
    assert "heading_path" in hit

    # İç uygulama alanlarının sızmadığı doğrulanır
    assert "embedding_text" not in hit
    assert "char_start" not in hit
    assert "char_end" not in hit


@pytest.mark.parametrize("invalid_k", [0, 21, -5, 100])
def test_search_invalid_k_returns_422(client: TestClient, invalid_k: int):
    """k parametresi 1..20 aralığı dışındaysa 422 Unprocessable Entity döner."""
    response = client.post(
        "/rag/search",
        json={"query": "test sorgusu", "k": invalid_k},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("empty_query", ["", "   ", "\t\n  "])
def test_search_empty_or_whitespace_query_returns_422(client: TestClient, empty_query: str):
    """Boş veya yalnızca boşluklardan oluşan sorgular 422 döner."""
    response = client.post(
        "/rag/search",
        json={"query": empty_query, "k": 5},
    )
    assert response.status_code == 422


def test_search_source_file_filter_isolates_document(client: TestClient):
    """source_file filtresi verildiğinde yalnızca eşleşen dosyanın sonuçları döner."""
    response = client.post(
        "/rag/search",
        json={
            "query": "hakları ve koşulları",
            "k": 5,
            "mode": "hybrid",
            "source_file": "sozlesme.pdf",
        },
    )
    assert response.status_code == 200
    hits = response.json()["hits"]
    assert len(hits) == 1
    assert hits[0]["source_file"] == "sozlesme.pdf"
    assert hits[0]["chunk_id"] == "chunk-sozlesme-1"


@pytest.mark.parametrize("mode", ["dense", "sparse", "hybrid"])
def test_search_all_modes_return_200(client: TestClient, mode: str):
    """dense, sparse ve hybrid modlarının tümü başarılı sonuç üretir."""
    response = client.post(
        "/rag/search",
        json={"query": "teslimat ve iade", "k": 2, "mode": mode},
    )
    assert response.status_code == 200
    assert len(response.json()["hits"]) > 0


def test_search_unindexed_collection_returns_503(
    fake_embedder: FakeEmbedder,
):
    """Koleksiyon henüz oluşturulmamışsa 503 ve anlaşılır hata mesajı döner."""
    empty_client = QdrantClient(":memory:")
    empty_config = QdrantConfig(
        url="http://localhost:6333",
        collection_prefix="unindexed_prefix",
    )
    unindexed_store = QdrantStore(
        client=empty_client, config=empty_config, embedder=fake_embedder
    )

    app.dependency_overrides[get_qdrant_store] = lambda: unindexed_store
    app.dependency_overrides[get_embedder] = lambda: fake_embedder

    with TestClient(app) as local_client:
        response = local_client.post(
            "/rag/search",
            json={"query": "herhangi bir soru", "k": 5},
        )
        assert response.status_code == 503
        detail = response.json().get("detail", "")
        assert "henüz indekslenmemiş" in detail

    app.dependency_overrides.clear()


def test_search_store_exception_returns_503_without_leaking_internals(
    memory_store: QdrantStore,
    fake_embedder: FakeEmbedder,
    monkeypatch: pytest.MonkeyPatch,
):
    """Store içinde beklenmeyen bir hata olduğunda 503 döner ve iç hata detayı sızdırılmaz."""
    # query_points metodunu hata fırlatacak şekilde monkeypatch yap
    def broken_query(*args, **kwargs):
        raise RuntimeError("qdrant://secret-user:super-password@internal-db:6333 connection died")

    monkeypatch.setattr(memory_store.client, "query_points", broken_query)

    app.dependency_overrides[get_qdrant_store] = lambda: memory_store
    app.dependency_overrides[get_embedder] = lambda: fake_embedder

    with TestClient(app) as local_client:
        response = local_client.post(
            "/rag/search",
            json={"query": "hata testi", "k": 5, "mode": "dense"},
        )
        assert response.status_code == 503
        detail = response.json().get("detail", "")
        # Şifre veya dahili URL sızmamalıdır
        assert "super-password" not in detail
        assert "internal-db" not in detail
        assert "bir hata oluştu" in detail

    app.dependency_overrides.clear()


def test_search_error_rfc7807_format(client: TestClient):
    """Hata cevapları RFC 7807 ProblemDetails standart formatında dönmelidir."""
    # 422 Unprocessable Entity testi
    res_422 = client.post("/rag/search", json={"query": "", "k": 5})
    assert res_422.status_code == 422
    assert "application/problem+json" in res_422.headers.get("content-type", "")
    body_422 = res_422.json()
    assert body_422["type"] == "about:blank"
    assert body_422["title"] == "Unprocessable Entity"
    assert body_422["status"] == 422
    assert body_422["instance"] == "/rag/search"
    assert "errors" in body_422
    assert isinstance(body_422["errors"], list)

    # 404 Not Found testi (Starlette routing hatası)
    res_404 = client.get("/non-existent-endpoint")
    assert res_404.status_code == 404
    assert "application/problem+json" in res_404.headers.get("content-type", "")
    body_404 = res_404.json()
    assert body_404["type"] == "about:blank"
    assert body_404["status"] == 404
    assert body_404["instance"] == "/non-existent-endpoint"

    # 405 Method Not Allowed testi
    res_405 = client.get("/rag/search")  # Sadece POST desteklenir
    assert res_405.status_code == 405
    assert "application/problem+json" in res_405.headers.get("content-type", "")
    body_405 = res_405.json()
    assert body_405["type"] == "about:blank"
    assert body_405["status"] == 405
    assert body_405["instance"] == "/rag/search"



# ============================================================================
# ENTEGRASYON TESTİ (GERÇEK DOCKER QDRANT İLE ÇALIŞTIRILIR)
# ============================================================================


@pytest.mark.integration
def test_search_integration_real_qdrant():
    """Gerçek Qdrant sunucusu (localhost:6333) üzerinde uçtan uca arama doğrulaması.

    Bu test `@pytest.mark.integration` ile işaretlidir. Yalnızca Docker ayağındayken çalışır.
    """
    import httpx

    # Önce Qdrant'ın ayakta olup olmadığını kontrol et
    try:
        ping = httpx.get("http://localhost:6333/readyz", timeout=2.0)
        if ping.status_code != 200:
            pytest.skip("Qdrant servisi hazır değil.")
    except Exception:
        pytest.skip("Docker üzerinde Qdrant çalışmıyor, entegrasyon testi atlandı.")

    client = QdrantClient(url="http://localhost:6333")
    embedder = FakeEmbedder(dimensions=16)
    config = QdrantConfig(
        url="http://localhost:6333",
        collection_prefix="integration_api_test",
    )
    store = QdrantStore(client=client, config=config, embedder=embedder)
    store.ensure_collection()

    chunk = Chunk(
        id="integ-chunk-1",
        text="Gerçek Qdrant entegrasyon test parçası.",
        embedding_text="Gerçek Qdrant entegrasyon test parçası.",
        source_file="integ.pdf",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=39,
        chunk_index=0,
        strategy="paragraph",
    )
    vec = embedder.embed_documents([chunk.embedding_text])
    store.upsert_chunks([chunk], vec, doc_hash="integ_hash")

    app.dependency_overrides[get_qdrant_store] = lambda: store
    app.dependency_overrides[get_embedder] = lambda: embedder

    try:
        with TestClient(app) as test_client:
            res = test_client.post(
                "/rag/search",
                json={"query": "entegrasyon", "k": 3, "mode": "hybrid"},
            )
            assert res.status_code == 200
            hits = res.json()["hits"]
            assert len(hits) == 1
            assert hits[0]["chunk_id"] == "integ-chunk-1"
    finally:
        app.dependency_overrides.clear()
        client.delete_collection(store.collection_name)


def test_search_error_rfc7807_format(client: TestClient):
    """Hata cevapları RFC 7807 ProblemDetails standart formatında dönmelidir."""
    # 422 Unprocessable Entity testi
    res_422 = client.post("/rag/search", json={"query": "", "k": 5})
    assert res_422.status_code == 422
    assert "application/problem+json" in res_422.headers.get("content-type", "")
    body_422 = res_422.json()
    assert body_422["type"] == "about:blank"
    assert body_422["title"] == "Unprocessable Entity"
    assert body_422["status"] == 422
    assert body_422["instance"] == "/rag/search"
    assert "errors" in body_422
    assert isinstance(body_422["errors"], list)

    # 404 Not Found testi (Starlette routing hatası)
    res_404 = client.get("/non-existent-endpoint")
    assert res_404.status_code == 404
    assert "application/problem+json" in res_404.headers.get("content-type", "")
    body_404 = res_404.json()
    assert body_404["type"] == "about:blank"
    assert body_404["status"] == 404
    assert body_404["instance"] == "/non-existent-endpoint"

    # 405 Method Not Allowed testi
    res_405 = client.get("/rag/search")  # Sadece POST desteklenir
    assert res_405.status_code == 405
    assert "application/problem+json" in res_405.headers.get("content-type", "")
    body_405 = res_405.json()
    assert body_405["type"] == "about:blank"
    assert body_405["status"] == 405
    assert body_405["instance"] == "/rag/search"

