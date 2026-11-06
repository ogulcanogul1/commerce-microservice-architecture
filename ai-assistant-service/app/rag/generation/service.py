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
    ValidationIssue,
)
from app.rag.generation.prompt import (
    build_messages,
    build_retry_messages,
)
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
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.llm = llm
        self.tokenizer = tokenizer
        self.config = config

    def retrieve(
        self,
        question: str,
        *,
        k: int,
        source_file: str | None = None,
    ) -> tuple[list[SearchHit], float | None]:
        """Execute synchronous vector retrieval and return hits alongside gate dense similarity score."""
        collection_name = self.store.collection_name
        if not self.store.client.collection_exists(collection_name):
            raise RuntimeError("Vektör koleksiyonu henüz indekslenmemiş.")

        filter_obj = SearchFilter(source_file=source_file) if source_file else None

        # 1. Embed query exactly ONCE
        query_vec = self.embedder.embed_query(question)

        # 2. Execute retrieval based on configured mode
        mode = self.config.retrieval_mode
        if mode == "dense":
            hits = search_dense(
                client=self.store.client,
                collection_name=collection_name,
                query_vec=query_vec,
                k=k,
                filter=filter_obj,
            )
        elif mode == "sparse":
            query_sparse = self.store.sparse_encoder.encode_query(question)
            hits = search_sparse(
                client=self.store.client,
                collection_name=collection_name,
                query_sparse=query_sparse,
                k=k,
                filter=filter_obj,
            )
        else:  # hybrid
            query_sparse = self.store.sparse_encoder.encode_query(question)
            hits = search_hybrid(
                client=self.store.client,
                collection_name=collection_name,
                query_vec=query_vec,
                query_sparse=query_sparse,
                k=k,
                filter=filter_obj,
            )

        # 3. Calculate gate score (Decision 5: gate inspects dense cosine score, not RRF)
        top_dense_score: float | None = None
        if self.config.min_dense_score is not None:
            if mode == "dense":
                top_dense_score = hits[0].score if hits else None
            else:
                dense_hits = search_dense(
                    client=self.store.client,
                    collection_name=collection_name,
                    query_vec=query_vec,
                    k=1,
                    filter=filter_obj,
                )
                top_dense_score = dense_hits[0].score if dense_hits else None

        return hits, top_dense_score

    async def answer(
        self,
        question: str,
        *,
        k: int | None = None,
        source_file: str | None = None,
        correlation_id: str | None = None,
    ) -> RagAnswer:
        """End-to-end RAG answer pipeline with grounding validation and retry."""
        t_total_start = time.perf_counter()
        retrieval_latency_ms = 0.0
        llm_latency_ms = 0.0

        final_answer: RagAnswer | None = None
        masked_q = ""
        has_pii = False
        pii_types: list[str] = []

        try:
            # 1. PII Masking: external LLM and embedder must never receive raw user secrets
            masked_q, pii_types = mask_pii(question)
            has_pii = len(pii_types) > 0

            # 2. Synchronous retrieval running in threadpool
            target_k = k if k is not None else self.config.top_k
            t_retrieval_start = time.perf_counter()
            hits, top_score = await run_in_threadpool(
                self.retrieve,
                masked_q,
                k=target_k,
                source_file=source_file,
            )
            retrieval_latency_ms = (time.perf_counter() - t_retrieval_start) * 1000

            retrieved_chunk_ids = [h.chunk.id for h in hits]

            # 3. Gate: No results -> abstain: no_results
            if not hits:
                final_answer = RagAnswer(
                    status="abstained",
                    answer=self.config.abstain_message,
                    abstain_reason="no_results",
                    attempts=0,
                    top_dense_score=top_score,
                    retrieved_chunk_ids=retrieved_chunk_ids,
                    context_chunk_ids=[],
                    validation_issues=[],
                    usage=TokenUsage(input_tokens=0, output_tokens=0),
                    provider=None,
                    model=None,
                )
                return final_answer

            # 4. Gate: Cosine similarity below threshold -> abstain: low_retrieval_score
            if self.config.min_dense_score is not None and (
                top_score is None or top_score < self.config.min_dense_score
            ):
                final_answer = RagAnswer(
                    status="abstained",
                    answer=self.config.abstain_message,
                    abstain_reason="low_retrieval_score",
                    attempts=0,
                    top_dense_score=top_score,
                    retrieved_chunk_ids=retrieved_chunk_ids,
                    context_chunk_ids=[],
                    validation_issues=[],
                    usage=TokenUsage(input_tokens=0, output_tokens=0),
                    provider=None,
                    model=None,
                )
                return final_answer

            # 5. Build context blocks according to token budget
            blocks = build_context(
                hits,
                tokenizer=self.tokenizer,
                budget=self.config.context_token_budget,
            )
            context_chunk_ids = [b.chunk.id for b in blocks]

            if not blocks:
                final_answer = RagAnswer(
                    status="abstained",
                    answer=self.config.abstain_message,
                    abstain_reason="no_results",
                    attempts=0,
                    top_dense_score=top_score,
                    retrieved_chunk_ids=retrieved_chunk_ids,
                    context_chunk_ids=[],
                    validation_issues=[],
                    usage=TokenUsage(input_tokens=0, output_tokens=0),
                    provider=None,
                    model=None,
                )
                return final_answer

            # 6. LLM Generation and Validation Loop (up to max_attempts)
            total_input_tokens = 0
            total_output_tokens = 0
            last_issues: list[ValidationIssue] = []
            last_content = ""
            last_provider: str | None = None
            last_model: str | None = None

            for attempt in range(1, self.config.max_attempts + 1):
                if attempt == 1:
                    messages = build_messages(masked_q, blocks)
                else:
                    messages = build_retry_messages(
                        masked_q,
                        blocks,
                        last_content,
                        last_issues,
                    )

                t_llm_start = time.perf_counter()
                resp = await asyncio.wait_for(
                    self.llm.generate(
                        messages,
                        temperature=self.config.temperature,
                        max_tokens=self.config.max_output_tokens,
                    ),
                    timeout=self.config.llm_timeout_sec,
                )
                llm_latency_ms += (time.perf_counter() - t_llm_start) * 1000

                last_content = resp.content
                last_provider = resp.provider
                last_model = resp.model

                if resp.usage:
                    if resp.usage.input_tokens is not None:
                        total_input_tokens += resp.usage.input_tokens
                    if resp.usage.output_tokens is not None:
                        total_output_tokens += resp.usage.output_tokens

                aggregated_usage = TokenUsage(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )

                # Check explicit model abstain refusal
                if is_abstain(resp.content):
                    final_answer = RagAnswer(
                        status="abstained",
                        answer=self.config.abstain_message,
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
                    )
                    return final_answer

                # Grounding validation
                issues = validate_answer(resp.content, blocks)
                if not issues:
                    # Valid grounded answer!
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
                    )
                    return final_answer

                # Validation failed on this attempt
                last_issues = issues

            # All attempts exhausted without passing validation -> abstain: validation_failed
            final_answer = RagAnswer(
                status="abstained",
                answer=self.config.abstain_message,
                abstain_reason="validation_failed",
                attempts=self.config.max_attempts,
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
            )
            return final_answer

        finally:
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
                    "latency_total_ms": round(total_latency_ms, 2),
                    "provider": final_answer.provider,
                    "model": final_answer.model,
                }
                if correlation_id:
                    log_data["correlation_id"] = correlation_id

                logger.info("RAG Answer Generation completed: %s", log_data)
