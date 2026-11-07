"""End-to-end evaluation runner for RAG generation quality.

Bu modül, eval/chunking/docs altındaki PDF dokümanlarını geçici bir koleksiyona indeksler,
eval/generation/answer_set.json içindeki soruları sırayla RagAnswerService üzerinden çalıştırır,
metrikleri hesaplar ve eval/generation/reports/<tarih>-<hash>.md ve .json formatında raporlar üretir.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import datetime
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import uuid

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qdrant_client import QdrantClient

from app.core.config import settings
from app.llm.base import BaseLLMProvider, ChatMessage
from app.llm.factory import LLMFactory
from app.llm.fake import FakeLLMProvider
from app.rag.chunking import DefaultChunker
from app.rag.chunking.models import Chunk, ChunkingConfig
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.embedding.base import Embedder
from app.rag.embedding.factory import get_default_embedder
from app.rag.embedding.fake import FakeEmbedder
from app.rag.evaluation.generation.dataset import (
    DEFAULT_ANSWER_SET_PATH,
    DEFAULT_GOLDEN_SET_PATH,
    AnswerCase,
    load_answer_set,
)
from app.rag.evaluation.generation.metrics import (
    CaseResult,
    GenerationEvalSummary,
    compute_generation_summary,
    score_case,
)
from app.rag.generation.models import GenerationConfig, RagAnswer
from app.rag.generation.service import RagAnswerService
from app.rag.ingestion.pdf.loader import PDFLoader
from app.rag.rerank.factory import get_reranker
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.store import QdrantStore

logger = logging.getLogger(__name__)

DEFAULT_REPORTS_DIR = Path("eval/generation/reports")


def get_git_commit_hash() -> str:
    """Mevcut git commit hash'ini ve çalışma dizininin temizlik durumunu döner."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        )
        h = out.decode("utf-8").strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
        )
        if status.strip():
            return f"{h} (dirty)"
        return h
    except Exception:
        return "unknown"


def load_eval_chunks(docs_dir: Path) -> list[Chunk]:
    """PDF dokümanlarını yükleyip DefaultChunker ile parçalar."""
    pdf_files = sorted(docs_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"{docs_dir} içinde PDF dokümanı bulunamadı.")

    loader = PDFLoader()
    tokenizer = TiktokenTokenizer()
    chunker = DefaultChunker(tokenizer=tokenizer, config=ChunkingConfig())

    chunks: list[Chunk] = []
    for pdf in pdf_files:
        doc = loader.load(pdf)
        chunks.extend(chunker.chunk(doc))
    return chunks


def setup_temporary_store(
    client: QdrantClient,
    embedder: Embedder,
    chunks: list[Chunk],
) -> tuple[QdrantStore, str]:
    """Geçici bir Qdrant koleksiyonu oluşturup chunk'ları indeksler."""
    col_name = f"geneval_run_{uuid.uuid4().hex[:8]}"
    config = QdrantConfig(
        url="http://localhost:6333",
        collection_prefix="eval",
        upsert_batch_size=50,
    )
    store = QdrantStore(
        client=client,
        config=config,
        embedder=embedder,
        collection_name=col_name,
    )
    store.ensure_collection(embedder=embedder, collection_name=col_name)
    store.ensure_payload_indexes()

    dense_vecs = embedder.embed_documents([c.embedding_text for c in chunks])
    store.upsert_chunks(chunks, dense_vecs, doc_hash="geneval_run_hash")
    return store, col_name


def make_fake_responder() -> Callable[[list[ChatMessage]], str]:
    """Smoke testler için kaynak 1'in ilk cümlesini [1] atfıyla dönen sahte cevaplayıcı."""
    def responder(messages: list[ChatMessage]) -> str:
        for msg in messages:
            if msg.role == "user":
                content = msg.content
                if "[1]" in content:
                    lines = content.splitlines()
                    for idx, line in enumerate(lines):
                        if line.startswith("[1] ("):
                            if idx + 1 < len(lines):
                                text = lines[idx + 1].strip()
                                first_sent = text.split(".")[0].strip()
                                if first_sent:
                                    return f"{first_sent} [1]."
                    return "Kaynak bilgisi uyarınca işlem yapılmıştır [1]."
        return "BULUNAMADI"

    return responder


def generate_markdown_report(
    summary: GenerationEvalSummary,
    results: list[CaseResult],
    meta: dict[str, Any],
) -> str:
    """Format evaluation results into a detailed GitHub-flavored Markdown report."""
    is_fake_llm = meta.get("is_fake_llm", False)
    git_hash = meta.get("git_commit", "unknown")
    run_date = meta.get("run_date", datetime.datetime.now().isoformat())

    md: list[str] = []
    md.append("# RAG Cevap Üretimi (Generation) Değerlendirme Raporu\n")

    if is_fake_llm:
        md.append("> [!WARNING]")
        md.append("> **Bu koşu smoke testtir, kalite sayısı değildir.**")
        md.append("> `--llm fake` seçeneği kullanılmıştır. Gerçek doğruluk için `--llm default` ile koşunuz.\n")

    # 1. Başlık Bilgileri
    md.append("## 1. Koşu Parametreleri ve Ortam Bilgisi\n")
    md.append(f"- **Tarih:** `{run_date}`")
    md.append(f"- **Git Commit:** `{git_hash}`")
    md.append(f"- **LLM Sağlayıcı / Model:** `{meta.get('llm_provider')}` / `{meta.get('llm_model')}`")
    md.append(f"- **Embedder:** `{meta.get('embedder')}`")
    md.append(f"- **RAG_MIN_DENSE_SCORE:** `{meta.get('min_dense_score')}`")
    md.append(f"- **RAG_TOP_K:** `{meta.get('top_k')}`")
    md.append(f"- **RAG_CONTEXT_TOKEN_BUDGET:** `{meta.get('token_budget')}`")
    rerank_setting = meta.get("rerank", "off")
    md.append(f"- **Reranker:** `{rerank_setting}`" + (f" ({meta.get('reranker_id')}, candidates={meta.get('rerank_candidates')})" if rerank_setting == "on" else ""))
    if meta.get("rerank_status_counts"):
        counts = meta["rerank_status_counts"]
        md.append(f"- **Rerank Durum Dağılımı:** `ok: {counts.get('ok', 0)}`, `failed: {counts.get('failed', 0)}`, `disabled: {counts.get('disabled', 0)}`")
        if counts.get("failed", 0) > 0:
            md.append("> [!WARNING]")
            md.append(f"> **UYARI:** {counts['failed']} soruda reranker çağrısı başarısız oldu!")
    md.append(f"- **Toplam Soru Sayısı:** `{summary.total_cases}` (Cevaplanabilir: `{summary.answerable_count}`, Cevaplanamaz: `{summary.unanswerable_count}`)\n")

    # 2. Özet Metrikler Tablosu
    md.append("## 2. Genel Kalite ve Maliyet Özeti\n")
    md.append("| Metrik | Değer | Açıklama |")
    md.append("| :--- | :--- | :--- |")
    md.append(f"| **Cevap Doğruluğu (Answer Accuracy)** | **%{summary.answer_accuracy * 100:.1f}** | Cevaplanabilir sorularda tam doğruluk (`correct`) oranı |")
    md.append(f"| **Halüsinasyon Oranı (Hallucination Rate)** | **%{summary.hallucination_rate * 100:.1f}** | Cevaplanamaz sorularda cevap verme oranı (**En pahalı hata**) |")
    md.append(f"| **Yanlış Abstain Oranı (False Abstain Rate)** | %{summary.false_abstain_rate * 100:.1f} | Cevaplanabilir sorularda gereksiz susma oranı |")
    md.append(f"| **Geçerli Atıf Oranı (Citation Valid Rate)** | %{summary.citation_valid_rate * 100:.1f} | Üretilen cevaplarda doğrulanmış atıf oranı |")
    md.append(f"| **Tekrar Deneme Oranı (Retry Rate)** | %{summary.retry_rate * 100:.1f} | İlk denemede doğrulanamayıp 2. denemeye giden soru oranı |")
    md.append(f"| **Ortalama Girdi Token (Input Tokens)** | {summary.avg_input_tokens:.1f} token | Soru ve kaynak bloklarının toplam prompt bütçesi |")
    md.append(f"| **Ortalama Çıktı Token (Output Tokens)** | {summary.avg_output_tokens:.1f} token | Üretilen cevap uzunluğu |")
    md.append(f"| **Gecikme p50 (Medyan)** | {summary.latency_p50_ms:.1f} ms | Medyan cevap üretim süresi |")
    md.append(f"| **Gecikme p95** | {summary.latency_p95_ms:.1f} ms | %95 persentil gecikme süresi |")
    if summary.errors_count > 0:
        md.append(f"| **Beklenmeyen Hatalar (Errors)** | {summary.errors_count} | İstisnalar nedeniyle puanlanamayan sorular |")
    md.append("")

    # Yanlış abstain detay kırılımı
    if summary.false_abstain_by_reason:
        md.append("**Yanlış Abstain Sebep Dağılımı:**")
        for reason, count in summary.false_abstain_by_reason.items():
            md.append(f"- `{reason}`: {count} soru")
        md.append("")

    # 3. Kategori Kırılımı Tablosu
    md.append("## 3. Soru Kategorisi Kırılımı\n")
    md.append("| Kategori | Toplam (n) | Doğru | Doğruluk | Not |")
    md.append("| :--- | :--- | :--- | :--- | :--- |")
    for cat_name, cat in summary.categories.items():
        warn_str = f"⚠️ `{cat.small_n_warning}`" if cat.small_n_warning else "✓ Güvenilir"
        md.append(f"| `{cat_name}` | {cat.total} | {cat.correct} | %{cat.accuracy * 100:.1f} | {warn_str} |")
    md.append("")

    # 4. Hata Analizi ve İnceleme Listeleri
    md.append("## 4. Hata İnceleme ve Güvenlik Analizi\n")

    # 4.0 Sistem Hataları
    error_cases = [r for r in results if r.error is not None]
    if error_cases:
        md.append(f"### 4.0 Çalışma Hatası Alan Sorular ({len(error_cases)})\n")
        for idx, ec in enumerate(error_cases, 1):
            md.append(f"{idx}. **[{ec.case_id}] Soru:** {ec.question}")
            md.append(f"   - **Hata Mesajı:** `{ec.error}`\n")

    # 4.1 Halüsinasyonlar (Cevaplanamaz iken cevap verilenler)
    hallucinations = [r for r in results if not r.answerable and r.status == "answered"]
    md.append(f"### 4.1 Halüsinasyon Üretilen Cevaplanamaz Sorular ({len(hallucinations)})\n")
    if hallucinations:
        for idx, h in enumerate(hallucinations, 1):
            md.append(f"{idx}. **[{h.case_id}] Soru:** {h.question}")
            md.append(f"   - **Üretilen Cevap:** {h.answer_text}")
            md.append(f"   - **Not:** {h.notes or 'Belirtilmemiş'}\n")
    else:
        md.append("✓ Harika! Hiçbir cevaplanamaz soru için uydurma cevap üretilmedi (Sıfır halüsinasyon).\n")

    # 4.2 Yanlış Abstain Edilen Sorular
    false_abstains = [r for r in results if r.answerable and r.status == "abstained"]
    md.append(f"### 4.2 Yanlış Abstain Edilen Cevaplanabilir Sorular ({len(false_abstains)})\n")
    if false_abstains:
        for idx, fa in enumerate(false_abstains, 1):
            md.append(f"{idx}. **[{fa.case_id}] Soru:** {fa.question}")
            md.append(f"   - **Abstain Sebebi:** `{fa.abstain_reason}`")
            md.append(f"   - **Beklenen Olgular:** {fa.expected_facts}\n")
    else:
        md.append("✓ Cevaplanabilir hiçbir soru gereksiz yere abstain edilmedi.\n")

    # 4.3 Eksik Olgu İçeren Sorular
    low_recalls = [r for r in results if r.answerable and r.status == "answered" and r.fact_recall < 1.0]
    md.append(f"### 4.3 Eksik Olgu İçeren Sorular (fact_recall < 1.0) ({len(low_recalls)})\n")
    if low_recalls:
        for idx, lr in enumerate(low_recalls, 1):
            md.append(f"{idx}. **[{lr.case_id}] Soru:** {lr.question}")
            md.append(f"   - **Beklenen Olgular:** {lr.expected_facts}")
            md.append(f"   - **Üretilen Cevap:** {lr.answer_text}")
            md.append(f"   - **Yakalama Oranı:** %{lr.fact_recall * 100:.1f}\n")
    else:
        md.append("✓ Üretilen tüm yanıtlarda beklenen tüm olgular eksiksiz yer aldı.\n")

    return "\n".join(md)


async def run_evaluation(
    service: RagAnswerService,
    cases: list[AnswerCase],
) -> list[CaseResult]:
    """Execute sequential RAG answering and scoring across all test cases."""
    results: list[CaseResult] = []

    print(f"[*] {len(cases)} soru sırayla değerlendiriliyor...")
    for idx, case in enumerate(cases, 1):
        start_time = time.perf_counter()
        error_msg = None
        rag_answer: RagAnswer | None = None
        try:
            rag_answer = await service.answer(
                question=case.question,
                k=service.config.top_k,
                correlation_id=f"eval-{case.id}",
            )
        except Exception as exc:
            error_msg = str(exc)
            rag_answer = None

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        case_res = score_case(case=case, answer=rag_answer, latency_ms=latency_ms, error=error_msg)
        results.append(case_res)

        status_flag = "✓" if case_res.correct else "✗"
        print(f"  [{idx}/{len(cases)}] {status_flag} {case.id} ({case_res.status}): {case.question[:45]}...")

    return results


def main() -> None:
    """CLI runner to execute RAG generation evaluation."""
    import anyio

    parser = argparse.ArgumentParser(description="RAG Generation Kalite Değerlendirme Koşucusu")
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("eval/chunking/docs"),
        help="PDF dokümanlarının dizini",
    )
    parser.add_argument(
        "--answer-set-path",
        type=Path,
        default=DEFAULT_ANSWER_SET_PATH,
        help="Answer set dosya yolu",
    )
    parser.add_argument(
        "--golden-path",
        type=Path,
        default=DEFAULT_GOLDEN_SET_PATH,
        help="Golden set dosya yolu",
    )
    parser.add_argument(
        "--llm",
        choices=["fake", "default"],
        default="fake",
        help="LLM sağlayıcısı: 'fake' (smoke test) veya 'default' (gerçek API)",
    )
    parser.add_argument(
        "--embedder",
        choices=["fake", "default"],
        default="default",
        help="Embedder sağlayıcısı",
    )
    parser.add_argument(
        "--client-mode",
        choices=["memory", "server"],
        default="memory",
        help="Qdrant modu: memory veya server",
    )
    parser.add_argument(
        "--min-dense-score",
        type=float,
        default=None,
        help="Abstain kapısı asgari dense skoru eşiği",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Retrieval top-k aday sayısı",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Raporların kaydedileceği dizin",
    )
    parser.add_argument(
        "--rerank",
        choices=["off", "on"],
        default="off",
        help="Reranker kullanımını aç/kapa (varsayılan: off)",
    )
    parser.add_argument(
        "--reranker",
        choices=["fake", "cross_encoder", "cohere"],
        default=None,
        help="Reranker sağlayıcısı (varsayılan: RAG_RERANK_PROVIDER)",
    )
    parser.add_argument(
        "--rerank-model",
        type=str,
        default="",
        help="Reranker özel model adı",
    )
    parser.add_argument(
        "--rerank-candidates",
        type=int,
        default=None,
        help="Retrieval'dan reranker'a iletilecek aday chunk sayısı",
    )

    args = parser.parse_args()

    # 1. Embedder Hazırla
    if args.embedder == "fake":
        embedder: Embedder = FakeEmbedder(dimensions=64)
        embedder_name = "FakeEmbedder(64d)"
    else:
        try:
            embedder = get_default_embedder()
            embedder_name = getattr(embedder, "model_id", "default")
        except Exception as exc:
            print(f"[HATA] Varsayilan embedder baslatilamadi: {exc}")
            print("Lutfen API anahtarlarinizi (.env) kontrol edin veya test icin '--embedder fake' kullanin.")
            sys.exit(1)

    # 2. LLM Hazırla
    is_fake_llm = args.llm == "fake"
    if is_fake_llm:
        responder = make_fake_responder()
        llm: BaseLLMProvider = FakeLLMProvider(responder=responder, model_name="fake-responder")
        llm_provider_name = "fake"
        llm_model_name = "fake-responder"
    else:
        provider_name = settings.RAG_LLM_PROVIDER or None
        model_name = settings.RAG_LLM_MODEL or None
        llm = LLMFactory.get_provider(provider_name, model_name=model_name)
        llm_provider_name = provider_name or "default"
        llm_model_name = getattr(llm, "model_name", "default")

    # 3. Qdrant İstemcisi
    if args.client_mode == "server":
        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    else:
        client = QdrantClient(":memory:")

    # 4. Dokümanları Yükle ve Geçici Koleksiyona İndeksle
    print("[*] PDF dokümanları yüklenip chunk'lara ayrılıyor...")
    chunks = load_eval_chunks(args.docs_dir)
    print(f"[*] Toplam {len(chunks)} chunk hazırlandı.")

    print("[*] Geçici koleksiyon kuruluyor ve indeksleniyor...")
    store, col_name = setup_temporary_store(client=client, embedder=embedder, chunks=chunks)

    # 5. RagAnswerService Yapılandır
    tokenizer = TiktokenTokenizer()
    gen_config = GenerationConfig.from_settings(settings)
    update_dict: dict[str, Any] = {}
    if args.min_dense_score is not None:
        update_dict["min_dense_score"] = args.min_dense_score
    if args.top_k is not None:
        update_dict["top_k"] = args.top_k

    reranker = None
    if args.rerank == "on":
        provider = args.reranker or getattr(settings, "RAG_RERANK_PROVIDER", "cross_encoder")
        model = args.rerank_model or getattr(settings, "RAG_RERANK_MODEL", "")
        reranker = get_reranker(provider, model_name=model or None)
        update_dict["rerank_enabled"] = True
        update_dict["rerank_fail_open"] = False  # Eval süreci her zaman fail-closed olmalıdır!
        update_dict["rerank_candidates"] = (
            args.rerank_candidates
            if args.rerank_candidates is not None
            else getattr(settings, "RAG_RERANK_CANDIDATES", 20)
        )

    if update_dict:
        gen_config = gen_config.model_copy(update=update_dict)

    service = RagAnswerService(
        store=store,
        embedder=embedder,
        llm=llm,
        tokenizer=tokenizer,
        config=gen_config,
        reranker=reranker,
    )

    try:
        # 6. Soruları Yükle ve Koş
        cases = load_answer_set(path=args.answer_set_path, golden_path=args.golden_path)
        results = anyio.run(run_evaluation, service, cases)

        # 7. Metrikleri Hesapla
        summary = compute_generation_summary(results)

        # 8. Raporları Kaydet
        args.reports_dir.mkdir(parents=True, exist_ok=True)
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_hash = uuid.uuid4().hex[:6]
        base_name = f"{now_str}_{run_hash}"

        rerank_status_counts = {"ok": 0, "failed": 0, "disabled": 0}
        for r in results:
            st = getattr(r, "rerank_status", None)
            if st in rerank_status_counts:
                rerank_status_counts[st] += 1

        meta = {
            "run_date": datetime.datetime.now().isoformat(),
            "git_commit": get_git_commit_hash(),
            "llm_provider": llm_provider_name,
            "llm_model": llm_model_name,
            "embedder": embedder_name,
            "is_fake_llm": is_fake_llm,
            "min_dense_score": gen_config.min_dense_score,
            "top_k": gen_config.top_k,
            "token_budget": gen_config.context_token_budget,
            "rerank": args.rerank,
            "reranker_id": getattr(reranker, "model_id", None) if reranker else None,
            "rerank_candidates": gen_config.rerank_candidates,
            "rerank_status_counts": rerank_status_counts,
        }

        md_content = generate_markdown_report(summary=summary, results=results, meta=meta)
        md_path = args.reports_dir / f"{base_name}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        json_path = args.reports_dir / f"{base_name}.json"
        json_payload = {
            "meta": meta,
            "summary": summary.model_dump(),
            "results": [r.model_dump() for r in results],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_payload, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 60)
        print(" KOŞU TAMAMLANDI")
        print("=" * 60)
        print(f"✓ Markdown Raporu: {md_path}")
        print(f"✓ JSON Verisi:     {json_path}")
        print(f"  Doğruluk:        %{summary.answer_accuracy * 100:.1f}")
        print(f"  Halüsinasyon:    %{summary.hallucination_rate * 100:.1f}")
        print(f"  Yanlış Abstain:  %{summary.false_abstain_rate * 100:.1f}")
        print("=" * 60 + "\n")

    finally:
        # 9. Geçici koleksiyonu mutlaka temizle
        try:
            client.delete_collection(col_name)
            print(f"[*] Geçici koleksiyon silindi: {col_name}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
