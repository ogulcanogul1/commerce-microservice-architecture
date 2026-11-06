"""Qdrant için Retriever protokol adaptörü (QdrantRetriever).

Bu sınıf, projenin mevcut 'Retriever' protokolüne (index, search, search_by_budget)
tam uyum sağlar. Bu sayede 'evaluate_retrieval' fonksiyonu ve değerlendirme
araçları, bellekteki BM25/Dense ile Qdrant'ı hiçbir kod değişikliği yapmadan
birebir kıyaslayabilir.
"""

from __future__ import annotations

from typing import Literal, Sequence
from app.rag.chunking.models import Chunk
from app.rag.chunking.tokenizer import Tokenizer
from app.rag.embedding.base import Embedder
from app.rag.evaluation.chunking.retrieval import select_chunks_by_budget
from app.rag.vectorstore.search import (
    SearchFilter,
    search_dense,
    search_hybrid,
    search_sparse,
)
from app.rag.vectorstore.store import QdrantStore


class QdrantRetriever:
    """Qdrant veritabanını standart Retriever protokolüne uyarlayan adaptör sınıfı."""

    def __init__(
        self,
        store: QdrantStore,
        embedder: Embedder,
        mode: Literal["dense", "sparse", "hybrid"] = "hybrid",
        filter: SearchFilter | None = None,
        doc_hash: str = "eval_temp_hash",
    ) -> None:
        """QdrantRetriever başlatıcı.

        Args:
            store: Yapılandırılmış QdrantStore nesnesi.
            embedder: Sorgu ve dokümanları vektörleştiren Embedder.
            mode: Arama modu ('dense', 'sparse' veya 'hybrid', varsayılan: 'hybrid').
            filter: Opsiyonel SearchFilter filtresi (source_file, sayfa aralığı).
            doc_hash: 'index' metodu çağrıldığında kullanılacak varsayılan doc_hash.
        """
        self.store = store
        self.embedder = embedder
        self.mode = mode
        self.filter = filter
        self.doc_hash = doc_hash

    def index(self, chunks: Sequence[Chunk]) -> None:
        """Verilen chunk'ları embed ederek Qdrant koleksiyonuna kaydeder.

        Değerlendirme (eval) veya geçici indeksleme amacıyla kullanılır.
        """
        if not chunks:
            return

        # 1. Doküman parçalarının embedding vektörlerini üret
        dense_vectors = self.embedder.embed_documents([c.embedding_text for c in chunks])

        # 2. QdrantStore üzerinden koleksiyona upsert et (sparse BM25 otomatik üretilir)
        self.store.upsert_chunks(
            chunks=chunks,
            dense_vectors=dense_vectors,
            doc_hash=self.doc_hash,
        )

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        """Verilen sorguya en benzer top-k doküman parçasını (Chunk) döner.

        Args:
            query: Doğal dil arama sorgusu.
            k: İstenen maksimum sonuç sayısı (varsayılan: 5).

        Returns:
            Eşleşen Chunk nesnelerinden oluşan liste.
        """
        if not query or not query.strip() or k <= 0:
            return []

        clean_query = query.strip()
        col_name = self.store.collection_name

        if self.mode == "dense":
            query_vec = self.embedder.embed_query(clean_query)
            hits = search_dense(
                client=self.store.client,
                collection_name=col_name,
                query_vec=query_vec,
                k=k,
                filter=self.filter,
            )
        elif self.mode == "sparse":
            query_sparse = self.store.sparse_encoder.encode_query(clean_query)
            hits = search_sparse(
                client=self.store.client,
                collection_name=col_name,
                query_sparse=query_sparse,
                k=k,
                filter=self.filter,
            )
        else:  # hybrid (default)
            query_vec = self.embedder.embed_query(clean_query)
            query_sparse = self.store.sparse_encoder.encode_query(clean_query)
            hits = search_hybrid(
                client=self.store.client,
                collection_name=col_name,
                query_vec=query_vec,
                query_sparse=query_sparse,
                k=k,
                filter=self.filter,
            )

        return [hit.chunk for hit in hits]

    def search_by_budget(
        self, query: str, budget: int, tokenizer: Tokenizer
    ) -> list[Chunk]:
        """Arama sonuçlarını belirli bir token bütçesini aşmayacak şekilde biriktirerek döner.

        Ortak 'select_chunks_by_budget' fonksiyonunu kullanır.
        """
        if not query or not query.strip() or budget <= 0:
            return []

        # Bütçeyi dolduracak kadar aday çek (üst sınır 50 ile sınırlandırılmıştır)
        candidate_limit = min(max(self.store.count(), 10), 50)
        ranked = self.search(query, k=candidate_limit)

        return select_chunks_by_budget(ranked, budget, tokenizer)
