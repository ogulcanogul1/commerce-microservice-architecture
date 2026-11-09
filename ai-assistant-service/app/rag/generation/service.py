"""Orchestration service combining PII masking, retrieval, context formatting, LLM generation, grounding validation, and retry logic."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from starlette.concurrency import run_in_threadpool

from app.core.pii import mask_pii
from app.llm.base import BaseLLMProvider, TokenUsage
from app.rag.chunking.tokenizer import Tokenizer
from app.rag.embedding.base import Embedder
from app.rag.generation.citations import cited_numbers, is_abstain, validate_answer
from app.rag.generation.context import build_context
from app.rag.generation.models import (
    Citation,
    GenerationConfig,
    RagAnswer,
    RetrievalOutcome,
    ValidationIssue,
)
from app.rag.generation.prompt import (
    build_messages,
    build_retry_messages,
)
from app.rag.rerank.apply import rerank_hits
from app.rag.rerank.base import Reranker
from app.rag.vectorstore.search import (
    SearchFilter,
    search_dense,
    search_hybrid,
    search_sparse,
)
from app.rag.vectorstore.store import QdrantStore

if TYPE_CHECKING:
    from app.rag.vectorstore.models import SearchHit

logger = logging.getLogger(__name__)


class RagAnswerService:
    """Production-grade RAG answer generation orchestrator."""

    def __init__(
        self,
        *,
        store: QdrantStore,
        embedder: Embedder,
        llm: BaseLLMProvider,
        tokenizer: Tokenizer,
        config: GenerationConfig,
        reranker: Reranker | None = None,
    ) -> None:
        # Gerekli tüm bileşenlerin bağımlılık enjeksiyonu (Dependency Injection) ile alınması
        self.store = store
        self.embedder = embedder
        self.llm = llm
        self.tokenizer = tokenizer
        self.config = config
        self.reranker = reranker

        if self.config.rerank_enabled and self.reranker is None:
            logger.warning(
                "RAG rerank_enabled=True olarak ayarlanmış ancak servise reranker örneği verilmemiş. "
                "Reranker devre dışı ('disabled') kalacaktır."
            )

    def retrieve_with_rerank(
        self,
        question: str,
        *,
        k: int,
        source_file: str | None = None,
        config: GenerationConfig | None = None,
    ) -> RetrievalOutcome:
        """Execute synchronous vector retrieval, apply optional reranking, and return complete outcome."""
        cfg = config or self.config

        # 1. Koleksiyonun veritabanında var olup olmadığını doğrula
        collection_name = self.store.collection_name
        if not self.store.client.collection_exists(collection_name):
            raise RuntimeError("Vektör koleksiyonu henüz indekslenmemiş.")

        # İsteğe bağlı dosya filtresi (SearchFilter) oluştur
        filter_obj = SearchFilter(source_file=source_file) if source_file else None

        # 2. Soru için embedding modelini YALNIZCA BİR KEZ çağır (Maliyet ve gecikme optimizasyonu)
        query_vec = self.embedder.embed_query(question)

        use_rerank = cfg.rerank_enabled and self.reranker is not None
        k_search = max(cfg.rerank_candidates, k) if use_rerank else k

        # 3. Ayarlanan arama moduna göre Qdrant üzerinde arama yap
        mode = cfg.retrieval_mode
        if mode == "dense":
            hits = search_dense(
                client=self.store.client,
                collection_name=collection_name,
                query_vec=query_vec,
                k=k_search,
                filter=filter_obj,
            )
        elif mode == "sparse":
            query_sparse = self.store.sparse_encoder.encode_query(question)
            hits = search_sparse(
                client=self.store.client,
                collection_name=collection_name,
                query_sparse=query_sparse,
                k=k_search,
                filter=filter_obj,
            )
        else:  # hybrid (Dense + BM25 Sparse RRF füzyonu)
            query_sparse = self.store.sparse_encoder.encode_query(question)
            hits = search_hybrid(
                client=self.store.client,
                collection_name=collection_name,
                query_vec=query_vec,
                query_sparse=query_sparse,
                k=k_search,
                filter=filter_obj,
            )

        # 4. Abstain Kapı Skoru (Karar 5):
        # RRF skoru sıralamadan türediği için alaka seviyesini göstermez;
        # bu yüzden kapı kontrolü için her zaman gerçek dense cosine benzerlik skoruna bakılır.
        top_dense_score: float | None = None
        if cfg.min_dense_score is not None:
            if mode == "dense":
                top_dense_score = hits[0].score if hits else None
            else:
                # Hibrit veya sparse modunda, aynı vektörle ek maliyetsiz en iyi 1 dense aday çekilir
                dense_hits = search_dense(
                    client=self.store.client,
                    collection_name=collection_name,
                    query_vec=query_vec,
                    k=1,
                    filter=filter_obj,
                )
                top_dense_score = dense_hits[0].score if dense_hits else None

        # 5. İsteğe bağlı Reranker adımı (İki aşamalı arama)
        if use_rerank and self.reranker is not None:
            t0 = time.perf_counter()
            reordered_hits, status, _ = rerank_hits(
                question,
                hits,
                self.reranker,
                top_k=k,
                fail_open=cfg.rerank_fail_open,
            )
            rerank_ms = (time.perf_counter() - t0) * 1000.0
            return RetrievalOutcome(
                hits=reordered_hits,
                top_dense_score=top_dense_score,
                rerank_status=status,
                rerank_candidates=len(hits),
                rerank_ms=rerank_ms,
            )

        return RetrievalOutcome(
            hits=hits[:k],
            top_dense_score=top_dense_score,
            rerank_status="disabled",
            rerank_candidates=0,
            rerank_ms=0.0,
        )

    def retrieve(
        self,
        question: str,
        *,
        k: int,
        source_file: str | None = None,
        config: GenerationConfig | None = None,
    ) -> tuple[list[SearchHit], float | None]:
        """Execute synchronous vector retrieval and return hits alongside gate dense similarity score."""
        outcome = self.retrieve_with_rerank(question, k=k, source_file=source_file, config=config)
        return outcome.hits, outcome.top_dense_score

    async def answer(
        self,
        question: str,
        *,
        k: int | None = None,
        source_file: str | None = None,
        correlation_id: str | None = None,
        config: GenerationConfig | None = None,
    ) -> RagAnswer:
        """End-to-end RAG answer pipeline with grounding validation and retry."""
        cfg = config or self.config
        t_total_start = time.perf_counter()
        retrieval_latency_ms = 0.0
        llm_latency_ms = 0.0
        rerank_ms = 0.0
        rerank_status: Literal["disabled", "ok", "failed"] = "disabled"
        rerank_candidates = 0

        final_answer: RagAnswer | None = None
        masked_q = ""
        has_pii = False
        pii_types: list[str] = []
        retrieved_chunk_ids: list[str] = []
        context_chunk_ids: list[str] = []
        top_score: float | None = None
        exc_occurred: Exception | None = None

        try:
            # -------------------------------------------------------------------------
            # 1. ADIM: PII Maskeleme (Kişisel Veri Koruması)
            # Kullanıcının TCKN, kredi kartı, IBAN vb. hassas verileri dış API'lara açık gitmez.
            # -------------------------------------------------------------------------
            masked_q, pii_types = mask_pii(question)
            has_pii = len(pii_types) > 0

            # -------------------------------------------------------------------------
            # 2. ADIM: Asenkron Threadpool Üzerinde Arama (Retrieval + Rerank)
            # Senkron Qdrant ve embedder çağrıları event loop'u kilitlemesin diye threadpool'a verilir.
            # -------------------------------------------------------------------------
            target_k = k if k is not None else cfg.top_k
            t_retrieval_start = time.perf_counter()
            outcome = await run_in_threadpool(
                self.retrieve_with_rerank,
                masked_q,
                k=target_k,
                source_file=source_file,
                config=cfg,
            )
            retrieval_latency_ms = (time.perf_counter() - t_retrieval_start) * 1000

            hits = outcome.hits
            top_score = outcome.top_dense_score
            rerank_status = outcome.rerank_status
            rerank_candidates = outcome.rerank_candidates
            rerank_ms = outcome.rerank_ms

            retrieved_chunk_ids = [h.chunk.id for h in hits]

            # -------------------------------------------------------------------------
            # 3. ADIM: Sonuçsuz Arama Kapısı (Fail-Fast Abstain)
            # Veritabanında eşleşen hiçbir kayıt yoksa LLM çağrılmadan hızlıca abstain dönülür.
            # -------------------------------------------------------------------------
            if not hits:
                final_answer = RagAnswer(
                    status="abstained",
                    answer=cfg.abstain_message,
                    abstain_reason="no_results",
                    attempts=0,
                    top_dense_score=top_score,
                    retrieved_chunk_ids=retrieved_chunk_ids,
                    context_chunk_ids=[],
                    validation_issues=[],
                    usage=TokenUsage(input_tokens=0, output_tokens=0),
                    provider=None,
                    model=None,
                    rerank_status=rerank_status,
                )
                return final_answer

            # -------------------------------------------------------------------------
            # 4. ADIM: Benzerlik Eşiği Kapısı (Low Retrieval Score)
            # Bulunan en iyi sonucun benzerlik skoru belirlenen eşiğin altındaysa,
            # modelin alakasız metinlerden uydurma yapmasını önlemek için doğrudan abstain edilir.
            # -------------------------------------------------------------------------
            if cfg.min_dense_score is not None and (
                top_score is None or top_score < cfg.min_dense_score
            ):
                final_answer = RagAnswer(
                    status="abstained",
                    answer=cfg.abstain_message,
                    abstain_reason="low_retrieval_score",
                    attempts=0,
                    top_dense_score=top_score,
                    retrieved_chunk_ids=retrieved_chunk_ids,
                    context_chunk_ids=[],
                    validation_issues=[],
                    usage=TokenUsage(input_tokens=0, output_tokens=0),
                    provider=None,
                    model=None,
                    rerank_status=rerank_status,
                )
                return final_answer

            # -------------------------------------------------------------------------
            # 5. ADIM: Context Bloklarının Oluşturulması ve Token Bütçesi
            # Aday chunk'lar [1], [2] diye numaralandırılır, prompt enjeksiyon etiketleri kaçırılır.
            # -------------------------------------------------------------------------
            blocks = build_context(
                hits,
                tokenizer=self.tokenizer,
                budget=cfg.context_token_budget,
            )
            context_chunk_ids = [b.chunk.id for b in blocks]

            if not blocks:
                final_answer = RagAnswer(
                    status="abstained",
                    answer=cfg.abstain_message,
                    abstain_reason="no_results",
                    attempts=0,
                    top_dense_score=top_score,
                    retrieved_chunk_ids=retrieved_chunk_ids,
                    context_chunk_ids=[],
                    validation_issues=[],
                    usage=TokenUsage(input_tokens=0, output_tokens=0),
                    provider=None,
                    model=None,
                    rerank_status=rerank_status,
                )
                return final_answer

            # -------------------------------------------------------------------------
            # 6. ADIM: LLM Yanıt Üretimi ve Doğrulama Döngüsü (En Fazla max_attempts)
            # -------------------------------------------------------------------------
            total_input_tokens = 0
            total_output_tokens = 0
            last_issues: list[ValidationIssue] = []
            last_content = ""
            last_provider: str | None = None
            last_model: str | None = None

            for attempt in range(1, cfg.max_attempts + 1):
                # İlk denemede standart prompt; sonraki denemelerde hataların bildirildiği retry prompt'u
                if attempt == 1:
                    messages = build_messages(masked_q, blocks)
                else:
                    messages = build_retry_messages(
                        masked_q,
                        blocks,
                        last_content,
                        last_issues,
                    )

                # LLM çağrısı zaman aşımı (timeout) korumasıyla çalıştırılır
                t_llm_start = time.perf_counter()
                resp = await asyncio.wait_for(
                    self.llm.generate(
                        messages,
                        temperature=cfg.temperature,
                        max_tokens=cfg.max_output_tokens,
                    ),
                    timeout=cfg.llm_timeout_sec,
                )
                llm_latency_ms += (time.perf_counter() - t_llm_start) * 1000

                last_content = resp.content
                last_provider = resp.provider
                last_model = resp.model

                # Harcanan token miktarlarını denemeler boyunca kümülatif topla
                if resp.usage:
                    if resp.usage.input_tokens is not None:
                        total_input_tokens += resp.usage.input_tokens
                    if resp.usage.output_tokens is not None:
                        total_output_tokens += resp.usage.output_tokens

                aggregated_usage = TokenUsage(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )

                # Model kaynaklarda bilginin olmadığını açıkça söylediyse ("BULUNAMADI"):
                # Israr edilmez, model tahmin yürütmeye zorlanmaz; doğrudan kurumsal mesajla abstain edilir.
                if is_abstain(resp.content):
                    final_answer = RagAnswer(
                        status="abstained",
                        answer=cfg.abstain_message,
                        abstain_reason="model_abstained",
                        attempts=attempt,
                        top_dense_score=top_score,
                        retrieved_chunk_ids=retrieved_chunk_ids,
                        context_chunk_ids=context_chunk_ids,
                        citations=[],
                        validation_issues=[],
                        usage=aggregated_usage,
                        provider=resp.provider,
                        model=resp.model,
                        rerank_status=rerank_status,
                    )
                    return final_answer

                # Kod seviyesinde atıf ve sayı doğrulama kontrolü
                issues = validate_answer(resp.content, blocks)
                if not issues:
                    # Başarılı ve kurallara tam uyan yanıt!
                    # Cevapta gerçekten geçen [n] numaraları gerçek chunk ve sayfa bilgileriyle eşlenir.
                    used_nums = cited_numbers(resp.content)
                    block_map = {b.number: b for b in blocks}
                    citations = [
                        Citation(
                            number=n,
                            chunk_id=block_map[n].chunk.id,
                            source_file=block_map[n].chunk.source_file,
                            page_start=block_map[n].chunk.page_start,
                            page_end=block_map[n].chunk.page_end,
                            heading_path=block_map[n].chunk.heading_path,
                        )
                        for n in used_nums
                        if n in block_map
                    ]

                    final_answer = RagAnswer(
                        status="answered",
                        answer=resp.content,
                        abstain_reason=None,
                        citations=citations,
                        attempts=attempt,
                        top_dense_score=top_score,
                        retrieved_chunk_ids=retrieved_chunk_ids,
                        context_chunk_ids=context_chunk_ids,
                        validation_issues=[],
                        usage=aggregated_usage,
                        provider=resp.provider,
                        model=resp.model,
                        rerank_status=rerank_status,
                    )
                    return final_answer

                # Doğrulama geçilemediyse bulunan sorunlar kaydedilir ve döngü bir sonraki retry'a geçer
                last_issues = issues

            # -------------------------------------------------------------------------
            # 7. ADIM: Tüm Denemeler Tükendi (Validation Failed)
            # Model atıf hatalarını düzeltemediğinde, hatalı cevabı müşteriye göstermek yerine
            # güvenli kurumsal abstain mesajı verilir.
            # -------------------------------------------------------------------------
            final_answer = RagAnswer(
                status="abstained",
                answer=cfg.abstain_message,
                abstain_reason="validation_failed",
                attempts=cfg.max_attempts,
                top_dense_score=top_score,
                retrieved_chunk_ids=retrieved_chunk_ids,
                context_chunk_ids=context_chunk_ids,
                citations=[],
                validation_issues=last_issues,
                usage=TokenUsage(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                ),
                provider=last_provider,
                model=last_model,
                rerank_status=rerank_status,
            )
            return final_answer

        except Exception as exc:
            exc_occurred = exc
            raise

        finally:
            # -------------------------------------------------------------------------
            # 8. ADIM: Yapılandırılmış Gözlemlenebilirlik (Structured Logging - Karar 13)
            # Güvenlik ve KVKK gereği kullanıcı sorusunun açık metni ASLA loglanmaz;
            # sadece soru uzunluğu, PII varlığı, gecikmeler ve token sayıları kaydedilir.
            # Kesinti ve istisnalarda da durum='error' olarak her halükarda loglanır.
            # -------------------------------------------------------------------------
            total_latency_ms = (time.perf_counter() - t_total_start) * 1000
            if final_answer is not None:
                log_data = {
                    "event": "rag_answer",
                    "status": final_answer.status,
                    "abstain_reason": final_answer.abstain_reason,
                    "attempts": final_answer.attempts,
                    "question_len": len(question),
                    "has_pii": has_pii,
                    "pii_types": pii_types,
                    "retrieved_chunk_ids": final_answer.retrieved_chunk_ids,
                    "context_chunk_ids": final_answer.context_chunk_ids,
                    "cited_chunk_ids": [c.chunk_id for c in final_answer.citations],
                    "top_dense_score": final_answer.top_dense_score,
                    "validation_issues_count": len(final_answer.validation_issues),
                    "validation_issue_types": list(
                        dict.fromkeys(i.type for i in final_answer.validation_issues)
                    ),
                    "input_tokens": final_answer.usage.input_tokens,
                    "output_tokens": final_answer.usage.output_tokens,
                    "latency_retrieval_ms": round(retrieval_latency_ms, 2),
                    "latency_llm_ms": round(llm_latency_ms, 2),
                    "latency_rerank_ms": round(rerank_ms, 2),
                    "latency_total_ms": round(total_latency_ms, 2),
                    "rerank_status": rerank_status,
                    "rerank_candidates": rerank_candidates,
                    "provider": final_answer.provider,
                    "model": final_answer.model,
                }
                if correlation_id:
                    log_data["correlation_id"] = correlation_id

                logger.info("RAG Answer Generation completed: %s", log_data)
            else:
                log_data = {
                    "event": "rag_answer",
                    "status": "error",
                    "error_type": type(exc_occurred).__name__ if exc_occurred else "Unknown",
                    "question_len": len(question),
                    "has_pii": has_pii,
                    "pii_types": pii_types,
                    "retrieved_chunk_ids": retrieved_chunk_ids,
                    "context_chunk_ids": context_chunk_ids,
                    "top_dense_score": top_score,
                    "latency_retrieval_ms": round(retrieval_latency_ms, 2),
                    "latency_llm_ms": round(llm_latency_ms, 2),
                    "latency_rerank_ms": round(rerank_ms, 2),
                    "latency_total_ms": round(total_latency_ms, 2),
                    "rerank_status": rerank_status,
                    "rerank_candidates": rerank_candidates,
                }
                if correlation_id:
                    log_data["correlation_id"] = correlation_id

                logger.error("RAG Answer Generation failed with error: %s", log_data)
