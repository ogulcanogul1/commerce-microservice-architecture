"""models.py ve mapping.py için birim testleri."""

import pytest
from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.embedding.fake import FakeEmbedder
from app.rag.ingestion.models import ElementType
from app.rag.vectorstore.mapping import chunk_point_id, chunk_to_payload, payload_to_chunk
from app.rag.vectorstore.models import QdrantConfig, SearchHit


def test_chunk_point_id_deterministic():
    """Aynı chunk_id her zaman aynı UUID'yi, farklı olanlar farklı UUID vermelidir."""
    cid = "a1b2c3d4e5f60718"
    uid1 = chunk_point_id(cid)
    uid2 = chunk_point_id(cid)
    assert uid1 == uid2
    assert len(uid1) == 36  # Standart UUID string uzunluğu: 8-4-4-4-12 = 36 karakter

    other_uid = chunk_point_id("f6e5d4c3b2a10718")
    assert uid1 != other_uid


def test_chunk_point_id_empty_raises():
    """Boş veya sadece boşluktan oluşan chunk_id hata fırlatmalıdır."""
    with pytest.raises(ValueError, match="boş olamaz"):
        chunk_point_id("")

    with pytest.raises(ValueError, match="boş olamaz"):
        chunk_point_id("   ")


def test_payload_roundtrip_lossless():
    """Chunk -> payload -> Chunk dönüşümü hiçbir alanı kaybetmeden birebir eşleşmelidir."""
    original = Chunk(
        id="c1a2b3c4d5e6f708",
        strategy=ChunkStrategy.STRUCTURE,
        source_file="docs/sozlesme.pdf",
        chunk_index=0,
        text="Bu bir Türkçe test dokümanıdır: ığüşöç İĞÜŞÖÇ. Ürün iade koşulları.",
        context_prefix="[Doküman: sozlesme.pdf | Sayfa: 1-2 | Bölüm 1 > İade Şartları]",
        page_start=1,
        page_end=2,
        element_types=[ElementType.PARAGRAPH, ElementType.HEADING],
        heading_path=["Bölüm 1", "İade Şartları"],
        char_start=100,
        char_end=250,
        token_count=35,
    )

    payload = chunk_to_payload(
        original,
        doc_hash="sha256_mock_hash",
        embedding_model_id="fake/deterministic-bow",
        ingested_at="2026-11-04T12:00:00Z",
    )

    # embedding_text payload'a yazılmamış olmalı (disk tasarrufu)
    assert "embedding_text" not in payload
    assert payload["doc_hash"] == "sha256_mock_hash"
    assert payload["heading_path"] == ["Bölüm 1", "İade Şartları"]

    # Geri dönüştür
    reconstructed = payload_to_chunk(payload)

    # Tüm alanlar birebir eşit olmalı
    assert reconstructed == original
    # Otomatik türetilen embedding_text de birebir aynı olmalı
    assert reconstructed.embedding_text == original.embedding_text


def test_qdrant_config_collection_name():
    """Farklı embedder ve modeller farklı koleksiyon isimleri üretmelidir."""
    embedder1 = FakeEmbedder(dimensions=64, model_id="fake/bow-model")
    config = QdrantConfig(collection_prefix="test_prefix")

    col_name = config.collection_name(embedder1)
    assert col_name == "test_prefix__fake_bow_model_64"

    embedder2 = FakeEmbedder(dimensions=128, model_id="fake/bow-model")
    assert config.collection_name(embedder2) != col_name

    embedder3 = FakeEmbedder(dimensions=64, model_id="fake/other-model")
    assert config.collection_name(embedder3) != col_name


def test_qdrant_config_validation():
    """Geçersiz parametreler Pydantic doğrulama hatası vermelidir."""
    with pytest.raises(Exception):
        QdrantConfig(upsert_batch_size=0)  # ge=1 kuralı

    with pytest.raises(Exception):
        QdrantConfig(timeout_sec=0)  # gt=0 kuralı


def test_search_hit_model():
    """SearchHit modeli dondurulmuş (frozen) ve doğru alanlara sahip olmalıdır."""
    chunk = Chunk(
        id="c1",
        strategy=ChunkStrategy.FIXED,
        source_file="d.pdf",
        chunk_index=0,
        text="Deneme",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=6,
        token_count=2,
    )
    hit = SearchHit(chunk=chunk, score=0.95, source="hybrid")
    assert hit.score == 0.95
    assert hit.source == "hybrid"
    assert hit.chunk.id == "c1"

    with pytest.raises(Exception):
        hit.score = 0.50  # frozen=True olduğu için değiştirilemez


def test_qdrant_config_create_client():
    """QdrantConfig.create_client() konfigürasyondaki parametrelerle QdrantClient üretmelidir."""
    config = QdrantConfig(
        url="http://test-server:6333",
        api_key="secret-key",
        timeout_sec=45.0,
    )
    client = config.create_client()
    assert client is not None


def test_payload_chunk_count_support():
    """chunk_to_payload chunk_count alanını desteklemeli ve payload_to_chunk ile kayıpsız dönmelidir."""
    original = Chunk(
        id="chunk_test_count",
        strategy=ChunkStrategy.STRUCTURE,
        source_file="docs/test.pdf",
        chunk_index=0,
        text="Örnek metin",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=11,
        token_count=2,
    )
    payload = chunk_to_payload(
        original,
        doc_hash="hash_123",
        embedding_model_id="fake-embedder",
        ingested_at="2026-11-06T12:00:00Z",
        chunk_count=5,
    )
    assert payload["chunk_count"] == 5

    reconstructed = payload_to_chunk(payload)
    assert reconstructed == original

