"""QdrantStore sınıfı için birim testleri."""

import pytest
from qdrant_client import QdrantClient

from app.rag.chunking.models import Chunk, ChunkStrategy
from app.rag.embedding.fake import FakeEmbedder
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.store import QdrantStore


def _make_chunk(cid: str, source_file: str, text: str, index: int = 0) -> Chunk:
    """Testler için geçerli ve minimal bir Chunk nesnesi üretir."""
    return Chunk(
        id=cid,
        strategy=ChunkStrategy.STRUCTURE,
        source_file=source_file,
        chunk_index=index,
        text=text,
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=len(text),
        token_count=len(text.split()),
    )


@pytest.fixture
def memory_store():
    """Hafıza içi (:memory:) Qdrant istemcisi ve FakeEmbedder ile donatılmış test store'u."""
    client = QdrantClient(":memory:")
    config = QdrantConfig(collection_prefix="test_store", upsert_batch_size=2)
    embedder = FakeEmbedder(dimensions=16, model_id="fake/test-model")
    store = QdrantStore(client=client, config=config, embedder=embedder)
    store.ensure_collection()
    store.ensure_payload_indexes()
    return store, client, embedder, config


def test_ensure_collection_idempotent(memory_store):
    """ensure_collection birden fazla kez çağrıldığında hata vermemeli ve koleksiyon korunmalıdır."""
    store, client, embedder, _ = memory_store

    # İkinci kez çağır
    col_name = store.ensure_collection(embedder)
    assert client.collection_exists(col_name)


def test_ensure_collection_dimension_mismatch_raises(memory_store):
    """Mevcut koleksiyon boyutu (16) ile farklı boyuttaki (32) embedder çağrısı ValueError fırlatmalıdır."""
    store, client, _, config = memory_store
    col_name = store.collection_name

    # Aynı koleksiyon adı için 32 boyutlu embedder ile çağır
    mismatched_embedder = FakeEmbedder(dimensions=32, model_id="fake/test-model")
    mismatched_store = QdrantStore(
        client=client,
        config=config,
        embedder=mismatched_embedder,
        collection_name=col_name,
    )

    with pytest.raises(ValueError, match="Koleksiyon boyutu uyuşmazlığı"):
        mismatched_store.ensure_collection()


def test_upsert_chunks_idempotent(memory_store):
    """Aynı chunk'ların tekrar upsert edilmesi point sayısını değiştirmemelidir (idempotent)."""
    store, _, embedder, _ = memory_store
    chunks = [
        _make_chunk("c1", "doc1.pdf", "İlk paragraf metni", 0),
        _make_chunk("c2", "doc1.pdf", "İkinci paragraf metni", 1),
    ]
    vectors = embedder.embed_documents([c.embedding_text for c in chunks])

    # İlk yazma
    written = store.upsert_chunks(chunks, vectors, doc_hash="hash_v1")
    assert written == 2
    assert store.count() == 2

    # İkinci kez aynı chunk'ları yaz (Point ID'ler deterministik uuid5 olduğu için üzerine yazar)
    written2 = store.upsert_chunks(chunks, vectors, doc_hash="hash_v1")
    assert written2 == 2
    assert store.count() == 2  # Sayı 4 değil, 2 kalmalıdır!


def test_upsert_batch_limit(memory_store):
    """upsert_batch_size=2 iken 5 chunk'ın eksiksiz ve hatasız yazıldığı doğrulanmalıdır."""
    store, _, embedder, _ = memory_store
    chunks = [_make_chunk(f"c_{i}", "doc.pdf", f"Metin {i}", i) for i in range(5)]
    vectors = embedder.embed_documents([c.embedding_text for c in chunks])

    written = store.upsert_chunks(chunks, vectors, doc_hash="hash_v1")
    assert written == 5
    assert store.count() == 5
    assert store.count("doc.pdf") == 5


def test_upsert_length_mismatch_raises(memory_store):
    """Chunk sayısı ile vektör sayısı uyuşmadığında ValueError fırlatılmalıdır."""
    store, _, embedder, _ = memory_store
    chunks = [_make_chunk("c1", "d.pdf", "Metin 1")]
    vectors = embedder.embed_documents(["Metin 1", "Metin 2"])  # 2 vektör

    with pytest.raises(ValueError, match="eşit olmalıdır"):
        store.upsert_chunks(chunks, vectors, doc_hash="h1")


def test_delete_stale_only_deletes_target_file_old_hash(memory_store):
    """delete_stale yalnızca hedef dosyanın eski hash'li point'lerini silmeli, başka dosyaya dokunmamalıdır."""
    store, _, embedder, _ = memory_store

    # Dosya A (v1)
    chunks_a_v1 = [_make_chunk("a1", "docA.pdf", "A v1 metin 1"), _make_chunk("a2", "docA.pdf", "A v1 metin 2")]
    vecs_a_v1 = embedder.embed_documents([c.embedding_text for c in chunks_a_v1])
    store.upsert_chunks(chunks_a_v1, vecs_a_v1, doc_hash="hash_A_v1")

    # Dosya B (v1)
    chunks_b = [_make_chunk("b1", "docB.pdf", "B metin 1")]
    vecs_b = embedder.embed_documents([c.embedding_text for c in chunks_b])
    store.upsert_chunks(chunks_b, vecs_b, doc_hash="hash_B_v1")

    assert store.count() == 3

    # Dosya A güncellendi -> v2 chunk'ları geldi
    chunks_a_v2 = [_make_chunk("a3", "docA.pdf", "A v2 metin 1"), _make_chunk("a4", "docA.pdf", "A v2 metin 2")]
    vecs_a_v2 = embedder.embed_documents([c.embedding_text for c in chunks_a_v2])
    store.upsert_chunks(chunks_a_v2, vecs_a_v2, doc_hash="hash_A_v2")

    # Şu an A'nın hem v1 (2 point) hem v2 (2 point) hali var + B (1 point) = 5 point
    assert store.count() == 5

    # Eski point'leri temizle: docA.pdf için hash_A_v2 olmayanları sil
    store.delete_stale("docA.pdf", keep_doc_hash="hash_A_v2")

    # Kontroller
    assert store.count("docA.pdf") == 2
    assert store.count("docB.pdf") == 1  # Dosya B'ye kesinlikle dokunulmamış olmalı
    assert store.count() == 3


def test_delete_document_and_get_doc_hash(memory_store):
    """delete_document tüm dokümanı silmeli; get_doc_hash doğru hash'i veya None dönmelidir."""
    store, _, embedder, _ = memory_store

    # Henüz dosya yokken get_doc_hash None dönmeli
    assert store.get_doc_hash("yok.pdf") is None

    chunks = [_make_chunk("c1", "sozlesme.pdf", "Sözleşme maddesi 1")]
    vecs = embedder.embed_documents([c.embedding_text for c in chunks])
    store.upsert_chunks(chunks, vecs, doc_hash="hash_sozlesme_123")

    # Kaydedildikten sonra get_doc_hash değeri vermeli
    assert store.get_doc_hash("sozlesme.pdf") == "hash_sozlesme_123"

    # Dokümanı tamamen sil
    store.delete_document("sozlesme.pdf")
    assert store.count("sozlesme.pdf") == 0
    assert store.get_doc_hash("sozlesme.pdf") is None
