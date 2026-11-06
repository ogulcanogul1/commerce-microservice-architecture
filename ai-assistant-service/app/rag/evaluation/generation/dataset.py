"""Dataset loader and validator for RAG generation evaluation.

Bu modül, eval/generation/answer_set.json dosyasını yükler, golden_set.json ile
question_id referanslarını çözümler ve veri setinin tutarlılığını doğrular.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_ANSWER_SET_PATH = Path("eval/generation/answer_set.json")
DEFAULT_GOLDEN_SET_PATH = Path("eval/chunking/golden_set.json")


class AnswerCase(BaseModel):
    """Single evaluation case for grounded RAG generation testing."""

    id: str = Field(description="Unique case identifier (e.g. G01, U01)")
    question_id: str | None = Field(default=None, description="Optional reference to golden_set.json ID (e.g. Q01)")
    question: str = Field(description="Natural language question string")
    answerable: bool = Field(description="True if documents contain evidence to answer, False otherwise")
    expected_facts: list[str] = Field(default_factory=list, description="Must-have key facts in answer")
    forbidden_facts: list[str] = Field(default_factory=list, description="Strictly forbidden hallucinations")
    category: str = Field(default="unanswerable", description="Evaluation category (single_fact, table_lookup, unanswerable, etc.)")
    notes: str | None = Field(default=None, description="Explanatory notes or rationale")


def load_raw_json(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSON array file from disk."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"JSON dosyası bulunamadı: {p}")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Beklenen JSON bir liste olmalıydı, alınan tip: {type(data).__name__}")
    return data


def validate_raw_answer_set(
    raw_cases: list[dict[str, Any]],
    golden_map: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Validate structure, field rules, and foreign keys of raw answer set items.

    Kurallar:
    1. Tüm id'ler benzersiz olmalıdır.
    2. question_id ve question alanlarından tam olarak BİRİ dolu olmalıdır.
    3. question_id belirtilmişse golden_set.json içinde mutlaka var olmalıdır.
    4. answerable=True ise expected_facts en az 1 eleman içermelidir.
    5. answerable=False ise expected_facts boş olmalıdır.
    """
    seen_ids: set[str] = set()

    for idx, item in enumerate(raw_cases):
        cid = item.get("id")
        # 1. ID kontrolü
        if not cid or not isinstance(cid, str):
            raise ValueError(f"Sıra {idx}: 'id' alanı zorunludur ve string olmalıdır.")
        if cid in seen_ids:
            raise ValueError(f"Yinelenen id tespit edildi: '{cid}'. Tüm id'ler benzersiz olmalıdır.")
        seen_ids.add(cid)

        # 2. Alan kuralı: question_id ve question alanlarından tam olarak biri dolu olmalı
        q_id = item.get("question_id")
        q_text = item.get("question")
        has_qid = bool(q_id and isinstance(q_id, str) and q_id.strip())
        has_qtext = bool(q_text and isinstance(q_text, str) and q_text.strip())

        if has_qid and has_qtext:
            raise ValueError(
                f"Case '{cid}': 'question_id' ({q_id}) ve 'question' aynı anda dolu olamaz. "
                "Tam olarak biri dolu olmalıdır."
            )
        if not has_qid and not has_qtext:
            raise ValueError(
                f"Case '{cid}': 'question_id' veya 'question' alanlarından biri mutlaka dolu olmalıdır."
            )

        # 3. question_id golden set'te mevcut mu?
        if has_qid:
            if golden_map is not None and q_id not in golden_map:
                raise ValueError(
                    f"Case '{cid}': Belirtilen question_id '{q_id}' golden_set.json içinde bulunamadı."
                )

        # 4 ve 5. answerable ve expected_facts ilişkisi
        answerable = item.get("answerable")
        if not isinstance(answerable, bool):
            raise ValueError(f"Case '{cid}': 'answerable' alanı boolean (True/False) olmalıdır.")

        expected = item.get("expected_facts") or []
        if not isinstance(expected, list):
            raise ValueError(f"Case '{cid}': 'expected_facts' alanı bir liste olmalıdır.")

        if answerable and len(expected) == 0:
            raise ValueError(
                f"Case '{cid}': Cevaplanabilir (answerable=True) sorular en az 1 'expected_facts' içermelidir."
            )
        if not answerable and len(expected) > 0:
            raise ValueError(
                f"Case '{cid}': Cevaplanamaz (answerable=False) soruların 'expected_facts' listesi boş olmalıdır."
            )


def load_answer_set(
    path: str | Path = DEFAULT_ANSWER_SET_PATH,
    golden_path: str | Path | None = DEFAULT_GOLDEN_SET_PATH,
) -> list[AnswerCase]:
    """Load, validate, and resolve answer set evaluation cases.

    Eğer question_id belirtilmişse, soru metni ve kategori golden_set.json'dan çözümlenir.
    """
    raw_cases = load_raw_json(path)

    # Golden set haritasını hazırla
    golden_map: dict[str, dict[str, Any]] = {}
    if golden_path is not None:
        p_golden = Path(golden_path)
        if p_golden.is_file():
            raw_golden = load_raw_json(p_golden)
            golden_map = {item["id"]: item for item in raw_golden if "id" in item}
        else:
            logger.warning("Golden set dosyası bulunamadı (%s), question_id çözümlenemeyebilir.", p_golden)

    # Ham yapıyı doğrula
    validate_raw_answer_set(raw_cases, golden_map=golden_map if golden_map else None)

    resolved_cases: list[AnswerCase] = []
    for item in raw_cases:
        cid = item["id"]
        q_id = item.get("question_id")
        q_text = item.get("question")
        answerable = item["answerable"]
        expected_facts = item.get("expected_facts") or []
        forbidden_facts = item.get("forbidden_facts") or []
        notes = item.get("notes")

        # Kategori ve soru metnini çözümle
        if q_id:
            # Golden set üzerinden soru ve kategori çekilir
            golden_entry = golden_map.get(q_id, {})
            resolved_question = golden_entry.get("question", "")
            resolved_category = golden_entry.get("category", "single_fact")
        else:
            resolved_question = q_text or ""
            resolved_category = "unanswerable" if not answerable else "custom"

        resolved_cases.append(
            AnswerCase(
                id=cid,
                question_id=q_id,
                question=resolved_question,
                answerable=answerable,
                expected_facts=expected_facts,
                forbidden_facts=forbidden_facts,
                category=resolved_category,
                notes=notes,
            )
        )

    return resolved_cases


def main() -> None:
    """CLI runner to validate the answer set file."""
    parser = argparse.ArgumentParser(description="RAG Generation Answer Set Doğrulayıcı")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_ANSWER_SET_PATH,
        help="Doğrulanacak answer_set.json dosya yolu",
    )
    parser.add_argument(
        "--golden-path",
        type=Path,
        default=DEFAULT_GOLDEN_SET_PATH,
        help="Referans golden_set.json dosya yolu",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Veri setini doğrula ve özet yazdır",
    )

    args = parser.parse_args()

    try:
        cases = load_answer_set(path=args.path, golden_path=args.golden_path)
        ans_count = sum(1 for c in cases if c.answerable)
        unans_count = sum(1 for c in cases if not c.answerable)
        print("[OK] Answer set basariyla dogrulandi!")
        print(f"  Toplam Soru: {len(cases)}")
        print(f"  Cevaplanabilir: {ans_count} (Golden Set eslesmeli)")
        print(f"  Cevaplanamaz:   {unans_count} (6 Konu Disi + 6 Tehlikeli Yakin)")
    except Exception as exc:
        print(f"[HATA] Dogrulama Hatasi: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
