"""Artımlı Senkronizasyon (Incremental Sync) ve Doküman Parmak İzi (Fingerprint) Modülü.

Bu modül, gereksiz embedding API çağrılarını ve maliyetleri önlemek amacıyla:
  1. Dokümanın içeriği, parser versiyonu ve chunking ayarlarından deterministik bir doc_hash üretir.
  2. Değişmeyen dokümanları atlar (0 maliyet, 'skipped').
  3. Değişen dokümanları önce yeni chunk'ları yazıp ardından eski point'leri silerek günceller ('replaced').
  4. Yeni dokümanları ekler ('created').
  5. Klasörden kaldırılmış dosyaları opsiyonel olarak Qdrant'tan temizler ('prune').
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Literal

from qdrant_client import models

from app.rag.chunking.base import Chunker
from app.rag.chunking.models import ChunkingConfig, ChunkStrategy
from app.rag.embedding.base import Embedder
from app.rag.ingestion.models import ParsedDocument
from app.rag.ingestion.pdf.loader import PDFLoader
from app.rag.vectorstore.models import QdrantConfig, SyncReport
from app.rag.vectorstore.store import QdrantStore

logger = logging.getLogger(__name__)


def compute_doc_fingerprint(
    doc: ParsedDocument,
    chunking_config: ChunkingConfig,
    strategy: str | ChunkStrategy,
) -> str:
    """Dokümanın içeriği, parser bilgileri ve chunking parametrelerinden deterministik SHA-256 üretir.

    Karar 7: Dosyanın ham bayt hash'i KULLANILMAZ. Çünkü bir PDF'in oluşturma tarihi
    veya metadata'sı değiştiğinde bayt hash'i değişir ancak içerik aynıdır.
    Burada doğrudan parse edilmiş elementlerin normalize metinleri, sayfa sınırları,
    başlık hiyerarşisi, parser sürümü ve chunking konfigürasyon karması kullanılır.

    Args:
        doc: Ayrıştırılmış doküman (ParsedDocument).
        chunking_config: Kullanılan ChunkingConfig konfigürasyonu.
        strategy: Uygulanan chunking stratejisi (örn: 'structure').

    Returns:
        64 karakterlik SHA-256 hex string (örn: 'a3f89b...').
    """
    strat_val = strategy.value if isinstance(strategy, ChunkStrategy) else str(strategy)
    config_hash = chunking_config.config_hash()

    # Normalize edilmiş yapısal element verileri
    elements_data = []
    for el in doc.elements:
        elements_data.append({
            "type": str(el.type),
            "text": el.text.strip(),
            "page_start": el.page_start,
            "page_end": el.page_end,
            "heading_path": el.heading_path,
        })

    payload = {
        "source_file": doc.source_file,
        "parser_name": doc.parser_name,
        "parser_version": doc.parser_version,
        "strategy": strat_val,
        "config_hash": config_hash,
        "elements": elements_data,
    }

    # Anahtarları sıralı JSON olarak serileştirip SHA-256 al
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def sync_document(
    doc: ParsedDocument,
    *,
    chunker: Chunker,
    embedder: Embedder,
    store: QdrantStore,
    chunking_config: ChunkingConfig | None = None,
    strategy: str | ChunkStrategy | None = None,
) -> Literal["skipped", "created", "replaced"]:
    """Tek bir ParsedDocument'ı Qdrant veritabanı ile artımlı (incremental) senkronize eder.

    İşlem Adımları:
      1. Karantina Kontrolü: Doküman kalitesi 'quarantine' statüsündeyse hata fırlatılır.
      2. Parmak İzi (Fingerprint) Hesabı: doc_hash hesaplanır.
      3. Durum Kontrolü (store.get_doc_hash):
         - Qdrant'taki hash ile güncel hash AYNIYSA -> 'skipped' (Embedder'a hiç gidilmez!).
      4. Güncelleme / Ekleme:
         - chunker.chunk(doc) ile parçalanır.
         - embedder.embed_documents ile dense vektörler alınır.
         - store.upsert_chunks ile yeni point'ler yazılır.
      5. Temizlik (Upsert-then-Delete):
         - Eğer eski bir hash varsa, store.delete_stale ile eski versiyon point'leri silinir -> 'replaced'.
         - Eski hash yoksa -> 'created'.

    Args:
        doc: İşlenecek ParsedDocument nesnesi.
        chunker: Dokümanı parçalayacak Chunker nesnesi.
        embedder: Metinleri vektörleştirecek Embedder nesnesi.
        store: Qdrant veritabanı yöneticisi (QdrantStore).
        chunking_config: İsteğe bağlı ChunkingConfig (belirtilmezse chunker'dan okunur).
        strategy: İsteğe bağlı strateji adı.

    Returns:
        'skipped' | 'created' | 'replaced' durumlarından biri.
    """
    # 1. Aşama: Karantina kontrolü
    if doc.quality and doc.quality.status == "quarantine":
        reasons_str = ", ".join(doc.quality.reasons) if doc.quality.reasons else "Bilinmeyen kalite sorunu"
        raise ValueError(f"Doküman karantinada olduğu için indekslenmedi: {reasons_str}")

    # Chunker özelliklerini al
    cfg = chunking_config or getattr(chunker, "config", ChunkingConfig())
    strat = strategy or getattr(chunker, "strategy", getattr(chunker, "name", "structure"))

    # 2. Aşama: Parmak izi hesapla
    fingerprint = compute_doc_fingerprint(doc, cfg, strat)

    # 3. Aşama: Qdrant'taki durumunu kontrol et
    # Yarım yazma / crash koruması: Sadece tek bir point'e bakmak yerine,
    # dokümanın eksiksiz yazıldığını ve eski/artık point kalmadığını doğrula.
    if store.is_document_intact(doc.source_file, expected_doc_hash=fingerprint):
        return "skipped"

    # Mevcut point sayısı (created vs replaced ayrımı için)
    existing_count = store.count(doc.source_file)

    # 4. Aşama: Doküman yeni veya değişmiş / yarım kalmış -> Chunk'la ve Embed et
    chunks = chunker.chunk(doc)
    if not chunks:
        return "skipped"

    dense_vectors = embedder.embed_documents([c.embedding_text for c in chunks])

    # Yeni chunk'ları veritabanına yaz
    store.upsert_chunks(chunks=chunks, dense_vectors=dense_vectors, doc_hash=fingerprint)

    # 5. Aşama: Eski versiyon veya artık point'leri temizle (Upsert-then-Delete)
    if existing_count > 0:
        store.delete_stale(source_file=doc.source_file, keep_doc_hash=fingerprint)
        return "replaced"

    return "created"


def _get_all_stored_source_files(store: QdrantStore) -> set[str]:
    """Koleksiyonda kayıtlı tüm benzersiz source_file isimlerini döner."""
    if not store.client.collection_exists(store.collection_name):
        return set()

    stored_files: set[str] = set()
    offset = None
    while True:
        points, next_offset = store.client.scroll(
            collection_name=store.collection_name,
            limit=250,
            offset=offset,
            with_payload=["source_file"],
            with_vectors=False,
        )
        for p in points:
            if p.payload and "source_file" in p.payload:
                stored_files.add(p.payload["source_file"])

        if next_offset is None:
            break
        offset = next_offset

    return stored_files


def sync_directory(
    docs_dir: Path | str,
    *,
    chunker: Chunker,
    embedder: Embedder,
    store: QdrantStore,
    prune: bool = False,
    dry_run: bool = False,
    loader: PDFLoader | None = None,
    chunking_config: ChunkingConfig | None = None,
    strategy: str | ChunkStrategy | None = None,
) -> SyncReport:
    """Belirtilen klasördeki tüm PDF dokümanlarını Qdrant ile senkronize eder.

    Args:
        docs_dir: PDF dokümanlarının bulunduğu dizin.
        chunker: Chunker nesnesi.
        embedder: Embedder nesnesi.
        store: QdrantStore nesnesi.
        prune: True ise klasörde artık bulunmayan eski dosyaların point'leri Qdrant'tan silinir (varsayılan: False).
        dry_run: True ise veritabanında hiçbir değişiklik yapmadan simüle eder.
        loader: PDFLoader nesnesi (varsayılan: PDFLoader()).
        chunking_config: Opsiyonel chunking yapılandırması.
        strategy: Opsiyonel strateji.

    Returns:
        SyncReport: {created, skipped, replaced, pruned, failed} istatistikleri.
    """
    directory = Path(docs_dir)
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Doküman dizini bulunamadı: {directory}")

    pdf_loader = loader or PDFLoader()
    report = SyncReport()

    # Koleksiyonun ve indekslerin varlığını garantiye al
    if not dry_run:
        store.ensure_collection(embedder)
        store.ensure_payload_indexes()

    # Klasördeki tüm PDF'leri bul
    pdf_files = sorted(directory.glob("**/*.pdf"))
    disk_source_files = {p.name for p in pdf_files}

    for pdf_path in pdf_files:
        try:
            # Dokümanı parse et
            doc = pdf_loader.load(pdf_path)

            # Karantina kontrolü
            if doc.quality and doc.quality.status == "quarantine":
                reasons = ", ".join(doc.quality.reasons) if doc.quality.reasons else "Kalite sorunu"
                report.failed.append((str(pdf_path), f"Quarantine: {reasons}"))
                continue

            if dry_run:
                # Dry run modunda sadece parmak izi ve sağlamlık kontrolü yap
                cfg = chunking_config or getattr(chunker, "config", ChunkingConfig())
                strat = strategy or getattr(chunker, "strategy", getattr(chunker, "name", "structure"))
                fingerprint = compute_doc_fingerprint(doc, cfg, strat)

                if store.is_document_intact(doc.source_file, expected_doc_hash=fingerprint):
                    report.skipped += 1
                elif store.count(doc.source_file) > 0:
                    report.replaced += 1
                else:
                    report.created += 1
            else:
                # Gerçek senkronizasyon
                result = sync_document(
                    doc,
                    chunker=chunker,
                    embedder=embedder,
                    store=store,
                    chunking_config=chunking_config,
                    strategy=strategy,
                )
                if result == "skipped":
                    report.skipped += 1
                elif result == "replaced":
                    report.replaced += 1
                elif result == "created":
                    report.created += 1

        except Exception as e:
            report.failed.append((str(pdf_path), str(e)))

    # Prune işlemi: Klasörde artık yer almayan (silinmiş) eski dosyaların temizlenmesi.
    # Yüklenemeyen veya karantinadaki dosyalar diskte var olduğu için asla prune edilmez!
    if prune:
        stored_files = _get_all_stored_source_files(store)
        stale_files = stored_files - disk_source_files
        for stale_file in stale_files:
            if not dry_run:
                store.delete_document(stale_file)
            report.pruned += 1

    return report


def main() -> None:
    """CLI giriş noktası."""
    parser = argparse.ArgumentParser(description="Qdrant Doküman Incremental Sync Aracı")
    parser.add_argument("--docs-dir", required=True, help="PDF dokümanlarının dizini")
    parser.add_argument(
        "--prune",
        action="store_true",
        default=False,
        help="Klasörde artık bulunmayan dokümanları Qdrant'tan sil",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Veritabanına yazmadan nelerin değişeceğini simüle et",
    )
    args = parser.parse_args()

    from app.core.config import get_settings
    from app.rag.chunking.factory import get_chunker
    from app.rag.chunking.tokenizer import TiktokenTokenizer
    from app.rag.embedding.factory import get_default_embedder

    settings = get_settings()
    config = QdrantConfig(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY or None,
        collection_prefix=settings.QDRANT_COLLECTION_PREFIX,
    )
    client = config.create_client()
    embedder = get_default_embedder()
    store = QdrantStore(client=client, config=config, embedder=embedder)

    chunking_config = ChunkingConfig()
    tokenizer = TiktokenTokenizer()
    chunker = get_chunker("structure", tokenizer, chunking_config)

    report = sync_directory(
        docs_dir=args.docs_dir,
        chunker=chunker,
        embedder=embedder,
        store=store,
        prune=args.prune,
        dry_run=args.dry_run,
    )

    print("\n--- Sync Tamamlandı ---")
    print(f"Oluşturulan (Created) : {report.created}")
    print(f"Atlanan (Skipped)     : {report.skipped}")
    print(f"Güncellenen (Replaced): {report.replaced}")
    print(f"Silinen (Pruned)      : {report.pruned}")
    if report.failed:
        print(f"Başarısız (Failed)    : {len(report.failed)}")
        for f, err in report.failed:
            print(f"  - {f}: {err}")


if __name__ == "__main__":
    main()
