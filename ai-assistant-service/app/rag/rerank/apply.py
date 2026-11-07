import logging
from collections.abc import Sequence
from typing import Literal
from app.rag.rerank.base import Reranker
from app.rag.rerank.models import RerankError, RerankResult
from app.rag.vectorstore.models import SearchHit

logger = logging.getLogger(__name__)


def rerank_hits(
    query: str,
    hits: Sequence[SearchHit],
    reranker: Reranker,
    *,
    top_k: int,
    fail_open: bool,
) -> tuple[list[SearchHit], Literal["ok", "failed"], list[RerankResult]]:
    """Retrieval aşamasından gelen SearchHit listesini Reranker ile yeniden sıralar.

    Args:
        query: Maskelenmiş kullanıcı sorusu.
        hits: İlk aşama retrieval eşleşmeleri.
        reranker: Reranker arayüzünü uygulayan nesne.
        top_k: Döndürülecek nihai SearchHit sayısı.
        fail_open: Hata anında orijinal sırayla devam edilsin mi (True: üretim, False: eval).

    Returns:
        (yeniden_siralanmis_hits, durum, rerank_sonuclari)
    """
    hits_list = list(hits)
    if not hits_list:
        return [], "ok", []

    docs = [h.chunk.embedding_text for h in hits_list]

    try:
        results = reranker.rerank(query, docs)
        reordered_hits = [hits_list[r.index] for r in results]
        return reordered_hits[:top_k], "ok", results
    except RerankError as exc:
        if not fail_open:
            raise
        logger.warning(
            "Reranker çağrısı başarısız oldu (fail-open devrede, orijinal sıra kullanılıyor): %s",
            type(exc).__name__,
        )
        return hits_list[:top_k], "failed", []
    except Exception as exc:
        if not fail_open:
            raise
        logger.error(
            "Reranker sırasında beklenmeyen hata oluştu (fail-open devrede, orijinal sıra kullanılıyor): %s",
            type(exc).__name__,
        )
        return hits_list[:top_k], "failed", []
