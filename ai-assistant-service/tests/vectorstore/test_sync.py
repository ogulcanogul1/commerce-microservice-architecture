"""sync.py için birim testleri."""

from pathlib import Path
import pytest
from qdrant_client import QdrantClient

from app.rag.chunking.base import Chunker
from app.rag.chunking.models import Chunk, ChunkStrategy, ChunkingConfig
from app.rag.embedding.fake import FakeEmbedder
from app.rag.ingestion.models import Element, ElementType, ParsedDocument, QualityReport
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.store import QdrantStore
from app.rag.vectorstore.sync import (
    compute_doc_fingerprint,
    sync_directory,
    sync_document,
)


class DummyChunker:
    """Birim testler için deterministik basit Chunker."""

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()
        self.name = "dummy"
        self.strategy = ChunkStrategy.STRUCTURE

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        chunks: list[Chunk] = []
        for idx, el in enumerate(doc.elements):
            chunks.append(
                Chunk(
                    id=f"{doc.source_file}_chk_{idx}",
                    strategy=self.strategy,
                    source_file=doc.source_file,
                    chunk_index=idx,
                    text=el.text,
                    page_start=el.page_start,
                    page_end=el.page_end,
                    char_start=0,
                    char_end=len(el.text),
                    token_count=len(el.text.split()),
                )
            )
        return chunks


def _make_parsed_doc(source_file: str, texts: list[str], status: str = "ok") -> ParsedDocument:
    """Testler için sentetik ParsedDocument oluşturur."""
    elements = [
        Element(
            type=ElementType.PARAGRAPH,
            text=t,
            page_start=1,
            page_end=1,
        )
        for t in texts
    ]
    quality = QualityReport(
        page_count=1,
        suspect_char_ratio=0.0,
        status="quarantine" if status == "quarantine" else "ok",
        reasons=["Bozuk karakter"] if status == "quarantine" else [],
    )
    return ParsedDocument(
        source_file=source_file,
        elements=elements,
        quality=quality,
        parser_name="test_parser",
        parser_version="1.0",
    )


@pytest.fixture
def sync_env():
    """Hafıza içi (:memory:) Qdrant store ve FakeEmbedder ortamı."""
    client = QdrantClient(":memory:")
    config = QdrantConfig(collection_prefix="test_sync")
    embedder = FakeEmbedder(dimensions=16, model_id="fake/sync-model")
    store = QdrantStore(client=client, config=config, embedder=embedder)
    store.ensure_collection()
    store.ensure_payload_indexes()
    chunker = DummyChunker()
    return store, embedder, chunker


def test_fingerprint_deterministic():
    """Aynı içeriğin iki farklı nesnesi aynı parmak izini vermelidir."""
    doc1 = _make_parsed_doc("a.pdf", ["Paragraf 1", "Paragraf 2"])
    doc2 = _make_parsed_doc("a.pdf", ["Paragraf 1", "Paragraf 2"])
    cfg = ChunkingConfig()

    fp1 = compute_doc_fingerprint(doc1, cfg, ChunkStrategy.STRUCTURE)
    fp2 = compute_doc_fingerprint(doc2, cfg, ChunkStrategy.STRUCTURE)
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256


def test_second_sync_skips_and_embedder_calls_zero(sync_env):
    """Aynı doküman 2. kez sync edildiğinde sonuç 'skipped' olmalı ve embedder hiç çağrılmamalıdır."""
    store, embedder, chunker = sync_env
    doc = _make_parsed_doc("doc1.pdf", ["Metin 1", "Metin 2"])

    # 1. Senkronizasyon (Oluşturma)
    res1 = sync_document(doc, chunker=chunker, embedder=embedder, store=store)
    assert res1 == "created"
    assert embedder.call_count == 1
    assert store.count("doc1.pdf") == 2

    # 2. Senkronizasyon (Doküman değişmedi)
    res2 = sync_document(doc, chunker=chunker, embedder=embedder, store=store)
    assert res2 == "skipped"
    # Embedder çağrı sayısı DEĞİŞMEMELİ (0 maliyet!)
    assert embedder.call_count == 1
    assert store.count("doc1.pdf") == 2


def test_modified_document_replaces_and_preserves_other_docs(sync_env):
    """Bir doküman değiştiğinde 'replaced' olmalı, eski point'ler silinmeli ve diğer dosyalar etkilenmemelidir."""
    store, embedder, chunker = sync_env

    doc_a = _make_parsed_doc("docA.pdf", ["A metni"])
    doc_b = _make_parsed_doc("docB.pdf", ["B metni"])

    sync_document(doc_a, chunker=chunker, embedder=embedder, store=store)
    sync_document(doc_b, chunker=chunker, embedder=embedder, store=store)
    assert store.count() == 2

    # doc_a güncellendi (paragraf değişti)
    doc_a_updated = _make_parsed_doc("docA.pdf", ["A metni GÜNCELLENDİ", "Yeni ek paragraf"])
    res = sync_document(doc_a_updated, chunker=chunker, embedder=embedder, store=store)

    assert res == "replaced"
    # docA artık 2 chunk'a sahip
    assert store.count("docA.pdf") == 2
    # docB hâlâ 1 chunk'a sahip (dokunulmadı!)
    assert store.count("docB.pdf") == 1
    assert store.count() == 3


def test_upsert_failure_preserves_old_points(sync_env, monkeypatch):
    """Yazma sırasında hata oluşursa eski point'ler silinmemelidir (Upsert-then-Delete garantisi)."""
    store, embedder, chunker = sync_env
    doc = _make_parsed_doc("doc.pdf", ["Orijinal metin"])

    sync_document(doc, chunker=chunker, embedder=embedder, store=store)
    assert store.count("doc.pdf") == 1

    # store.upsert_chunks metodunun istisna fırlatmasını sağla (ağ hatası simülasyonu)
    def fail_upsert(*args, **kwargs):
        raise RuntimeError("Qdrant ağ hatası!")

    monkeypatch.setattr(store, "upsert_chunks", fail_upsert)

    doc_updated = _make_parsed_doc("doc.pdf", ["Yeni metin"])
    with pytest.raises(RuntimeError, match="Qdrant ağ hatası"):
        sync_document(doc_updated, chunker=chunker, embedder=embedder, store=store)

    # Eski point SİLİNMEMİŞ olmalı!
    assert store.count("doc.pdf") == 1


def test_quarantine_document_rejected(sync_env):
    """Karantinada olan doküman sync_document tarafından reddedilmelidir."""
    store, embedder, chunker = sync_env
    doc = _make_parsed_doc("bad.pdf", ["Bozuk metin"], status="quarantine")

    with pytest.raises(ValueError, match="Doküman karantinada"):
        sync_document(doc, chunker=chunker, embedder=embedder, store=store)


def test_sync_directory_with_prune_and_dry_run(sync_env, tmp_path):
    """sync_directory; dry_run, quarantine ve prune davranışlarını doğru yürütmelidir."""
    store, embedder, chunker = sync_env

    # 1. Geçici bir klasör oluştur ve 2 adet sahte PDF koy
    doc1_path = tmp_path / "doc1.pdf"
    doc2_path = tmp_path / "doc2.pdf"
    doc1_path.write_text("dummy 1")
    doc2_path.write_text("dummy 2")

    class FakeLoader:
        def load(self, p: Path):
            name = p.name
            if name == "doc1.pdf":
                return _make_parsed_doc("doc1.pdf", ["Doc 1 metni"])
            elif name == "doc2.pdf":
                return _make_parsed_doc("doc2.pdf", ["Doc 2 metni"])
            elif name == "quarantine.pdf":
                return _make_parsed_doc("quarantine.pdf", ["Bozuk"], status="quarantine")
            return _make_parsed_doc(name, ["Metin"])

    loader = FakeLoader()

    # Dry-run testi: Qdrant'a hiçbir şey yazılmamalı
    report_dry = sync_directory(
        docs_dir=tmp_path,
        chunker=chunker,
        embedder=embedder,
        store=store,
        dry_run=True,
        loader=loader,
    )
    assert report_dry.created == 2
    assert store.count() == 0  # Dry-run olduğu için boş kalır

    # Gerçek çalıştırma
    report = sync_directory(
        docs_dir=tmp_path,
        chunker=chunker,
        embedder=embedder,
        store=store,
        prune=False,
        loader=loader,
    )
    assert report.created == 2
    assert report.skipped == 0
    assert store.count() == 2

    # İkinci koşuda ikisi de skipped olmalı
    report_second = sync_directory(
        docs_dir=tmp_path,
        chunker=chunker,
        embedder=embedder,
        store=store,
        prune=False,
        loader=loader,
    )
    assert report_second.skipped == 2
    assert report_second.created == 0

    # Prune testi: doc2.pdf dosyasını klasörden sil ve prune=True ile koş
    doc2_path.unlink()

    report_prune = sync_directory(
        docs_dir=tmp_path,
        chunker=chunker,
        embedder=embedder,
        store=store,
        prune=True,
        loader=loader,
    )
    assert report_prune.skipped == 1  # doc1.pdf yerinde
    assert report_prune.pruned == 1   # doc2.pdf silindi
    assert store.count("doc2.pdf") == 0
    assert store.count("doc1.pdf") == 1


def test_interrupted_write_recovered_on_next_sync(sync_env):
    """Yazma işlemi yarıda kesilirse, sonraki sync yarım kalmış dokümanı tespit edip onarmalıdır."""
    store, embedder, chunker = sync_env

    doc_v1 = _make_parsed_doc("contract.pdf", ["M1", "M2", "M3", "M4"])
    res1 = sync_document(doc_v1, chunker=chunker, embedder=embedder, store=store)
    assert res1 == "created"
    assert store.count("contract.pdf") == 4

    # v2: 6 paragraflık yeni doküman
    doc_v2 = _make_parsed_doc("contract.pdf", ["Yeni 1", "Yeni 2", "Yeni 3", "Yeni 4", "Yeni 5", "Yeni 6"])
    cfg = ChunkingConfig()
    fp2 = compute_doc_fingerprint(doc_v2, cfg, ChunkStrategy.STRUCTURE)

    # Simülasyon: v2 yazılırken süreç ilk 2 chunk'tan sonra çöktü (batch crash)
    from app.rag.vectorstore.mapping import chunk_point_id, chunk_to_payload
    from qdrant_client import models

    v2_chunks = chunker.chunk(doc_v2)
    v2_vecs = embedder.embed_documents([c.embedding_text for c in v2_chunks[:2]])

    crashed_points = []
    for c, v in zip(v2_chunks[:2], v2_vecs):
        p = chunk_to_payload(
            c,
            doc_hash=fp2,
            embedding_model_id=embedder.model_id,
            ingested_at="2026-11-06T12:00:00Z",
            chunk_count=6,
        )
        crashed_points.append(
            models.PointStruct(
                id=chunk_point_id(c.id),
                vector={"dense": list(v), "sparse": models.SparseVector(indices=[], values=[])},
                payload=p,
            )
        )
    store.client.upsert(collection_name=store.collection_name, points=crashed_points)

    # Şu anda veritabanında 2 adet v2 parçası ve 2 adet henüz silinmemiş v1 parçası var
    # (İlk 2 chunk id bazında overwrite edildi, kalan 2 v1 parçası ise eski doc_hash ile duruyor)
    assert store.count("contract.pdf") == 4
    # Eski get_doc_hash() rastgele tek bir point'e bakıp v2'yi görebilir ve dokümanı tamamlanmış sanabilirdi!
    # Yeni is_document_intact kontrolü sayesinde doküman sağlam sayılmaz:
    assert store.is_document_intact("contract.pdf", expected_doc_hash=fp2) is False

    # Yeni sync başlatılır: Doküman "skipped" OLMAMALI, "replaced" olarak onarılmalıdır!
    res2 = sync_document(doc_v2, chunker=chunker, embedder=embedder, store=store)
    assert res2 == "replaced"

    # Onarım sonrası kontroller:
    # Toplam point sayısı tam olarak 6 olmalı (v2'nin tüm parçaları)
    assert store.count("contract.pdf") == 6
    # v1'den kalan 4 eski parça silinmiş olmalı:
    stale_remaining = store.client.count(
        collection_name=store.collection_name,
        count_filter=models.Filter(
            must=[models.FieldCondition(key="source_file", match=models.MatchValue(value="contract.pdf"))],
            must_not=[models.FieldCondition(key="doc_hash", match=models.MatchValue(value=fp2))],
        ),
        exact=True,
    ).count
    assert stale_remaining == 0
    assert store.is_document_intact("contract.pdf", expected_doc_hash=fp2) is True

    # Artık eksiksiz olduğu için sonraki sync "skipped" dönmeli
    res3 = sync_document(doc_v2, chunker=chunker, embedder=embedder, store=store)
    assert res3 == "skipped"


def test_prune_does_not_delete_files_existing_on_disk(tmp_path, sync_env):
    """--prune, diskte var olan ancak parse/yükleme hatası alan dosyaları Qdrant'tan silmemelidir."""
    store, embedder, chunker = sync_env

    # 1. Başlangıçta diskte doc1.pdf ve doc_error.pdf var
    p1 = tmp_path / "doc1.pdf"
    p1.write_text("ok")
    p2 = tmp_path / "doc_error.pdf"
    p2.write_text("error")

    class FaultyLoader:
        def load(self, p: Path):
            if p.name == "doc1.pdf":
                return _make_parsed_doc("doc1.pdf", ["İçerik 1"])
            elif p.name == "doc_error.pdf":
                # Diskte var ama yükleme hatası alıyor
                raise RuntimeError("PDF corrupt")
            raise FileNotFoundError()

    loader = FaultyLoader()

    # Önce doc1'i indeksle
    report = sync_directory(
        docs_dir=tmp_path,
        chunker=chunker,
        embedder=embedder,
        store=store,
        prune=True,
        loader=loader,
    )
    assert report.created == 1
    assert len(report.failed) == 1
    assert report.pruned == 0  # doc_error diskte olduğu için ASLA prune edilmedi!


def test_first_run_dry_run_collection_not_found_handled_safely(tmp_path):
    """Koleksiyon henüz hiç oluşturulmamışken --dry-run çalıştırıldığında hata fırlatmamalı ve created saymalıdır."""
    p = tmp_path / "doc.pdf"
    p.write_text("dummy")

    client = QdrantClient(":memory:")
    config = QdrantConfig(collection_prefix="fresh_uncreated_coll")
    embedder = FakeEmbedder(dimensions=16)
    store = QdrantStore(client=client, config=config, embedder=embedder)
    chunker = DummyChunker()

    class FreshLoader:
        def load(self, p: Path):
            return _make_parsed_doc("doc.pdf", ["Paragraf 1"])

    report = sync_directory(
        docs_dir=tmp_path,
        chunker=chunker,
        embedder=embedder,
        store=store,
        dry_run=True,
        loader=FreshLoader(),
    )
    assert report.created == 1
    assert len(report.failed) == 0
    assert report.skipped == 0


def test_subdirectories_with_same_filename_do_not_collide(tmp_path, sync_env):
    """Farklı alt dizinlerdeki aynı isimli PDF'ler (a/x.pdf ve b/x.pdf) birbirini ezmemeli ve skipped olmalıdır."""
    store, embedder, chunker = sync_env

    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()

    file_a = dir_a / "contract.pdf"
    file_b = dir_b / "contract.pdf"
    file_a.write_text("a")
    file_b.write_text("b")

    class SubdirLoader:
        def load(self, p: Path):
            # Dosya adını değil göreli yolu test et
            text = "A sözleşmesi içeriği" if "dir_a" in str(p) else "B sözleşmesi içeriği"
            return _make_parsed_doc(p.name, [text])

    loader = SubdirLoader()

    # 1. Koşu: İki dosya da oluşturulmalı (created=2, replaced=0)
    report1 = sync_directory(
        docs_dir=tmp_path,
        chunker=chunker,
        embedder=embedder,
        store=store,
        loader=loader,
    )
    assert report1.created == 2
    assert report1.replaced == 0
    assert report1.skipped == 0
    assert store.count("dir_a/contract.pdf") == 1
    assert store.count("dir_b/contract.pdf") == 1
    assert store.count() == 2

    # 2. Koşu: İkisi de değişmediği için SKIPPED olmalı (asla replaced veya re-embed olmamalı!)
    report2 = sync_directory(
        docs_dir=tmp_path,
        chunker=chunker,
        embedder=embedder,
        store=store,
        loader=loader,
    )
    assert report2.skipped == 2
    assert report2.created == 0
    assert report2.replaced == 0
    assert store.count() == 2


def test_sync_emptied_document_cleans_up_old_points(sync_env):
    """İçeriği tamamen boşaltılan bir doküman, eski point'lerini temizlemeli ve replaced dönmelidir."""
    store, embedder, chunker = sync_env

    # 1. Başlangıçta dolu bir doküman
    doc_initial = _make_parsed_doc("emptyable.pdf", ["Madde 1", "Madde 2", "Madde 3"])
    res1 = sync_document(doc_initial, chunker=chunker, embedder=embedder, store=store)
    assert res1 == "created"
    assert store.count("emptyable.pdf") == 3

    # 2. Dokümanın tüm içeriği silinmiş (0 element)
    doc_emptied = _make_parsed_doc("emptyable.pdf", [])
    res2 = sync_document(doc_emptied, chunker=chunker, embedder=embedder, store=store)
    assert res2 == "replaced"
    # Eski point'lerin tamamı silinmiş olmalı
    assert store.count("emptyable.pdf") == 0

    # 3. İkinci koşuda doküman zaten boş ve point yok, skipped dönmeli
    res3 = sync_document(doc_emptied, chunker=chunker, embedder=embedder, store=store)
    assert res3 == "skipped"


def test_sync_cli_main_help(monkeypatch):
    """sync CLI main() fonksiyonu NameError vermeden argparse yardımını açmalıdır."""
    import sys
    from app.rag.vectorstore.sync import main

    monkeypatch.setattr(sys, "argv", ["sync", "--help"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0

