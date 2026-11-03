import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, field_validator


QuestionCategory = Literal[
    "single_fact",
    "exception",
    "table_lookup",
    "table_cross_page",
    "cross_page_sentence",
    "heading_dependent",
]


class GoldenQuestion(BaseModel):
    """Altın veri seti (Golden Set) soru ve kanıt modeli."""
    id: str = Field(description="Tekil soru ID'si (örn: Q01)")
    question: str = Field(description="Test sorusu")
    doc: str = Field(description="İlgili dokümanın eval/chunking/docs altındaki dosya adı")
    evidence: list[str] = Field(
        min_length=1,
        description="Sorunun cevabını içeren birebir metin parçaları (ingestion element çıktısından)",
    )
    category: QuestionCategory = Field(description="Sorunun hedeflediği zorluk/zafiyet kategorisi")
    notes: str = Field(default="", description="Opsiyonel açıklama ve tasarım notları")

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Soru boş olamaz.")
        return v.strip()


def normalize_for_match(text: str) -> str:
    """Türkçe-duyarlı eşleştirme normalizasyonu.

    1. Unicode NFC normalizasyonu yapar.
    2. Türkçe büyük harfleri doğru küçük harfe çevirir (İ -> i, I -> ı).
    3. Tüm ardışık boşlukları tek bir standart boşluğa indirger.
    """
    if not text:
        return ""

    # 1. Unicode NFC
    normalized = unicodedata.normalize("NFC", text)

    # 2. Türkçe-duyarlı harf dönüşümü
    normalized = normalized.replace("İ", "i").replace("I", "ı")
    normalized = normalized.lower()

    # 3. Boşlukları sadeleştir
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def load_golden_set(json_path: Path | str) -> list[GoldenQuestion]:
    """JSON dosyasından GoldenQuestion listesini yükler ve doğrular."""
    path = Path(json_path)
    if not path.is_file():
        raise FileNotFoundError(f"Golden set dosyası bulunamadı: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Golden set JSON formatı bir liste olmalıdır.")

    return [GoldenQuestion.model_validate(item) for item in data]


def validate_golden_set(json_path: Path, docs_dir: Path) -> tuple[bool, list[str]]:
    """Golden set sorularını, kategorilerini ve dokümanlardaki kanıtları doğrular."""
    errors: list[str] = []
    questions = load_golden_set(json_path)

    if len(questions) < 40:
        errors.append(f"Yetersiz soru sayısı: {len(questions)} bulundu, en az 40 soru gerekli.")

    # Kategori dağılımını kontrol et
    categories = [
        "single_fact",
        "exception",
        "table_lookup",
        "table_cross_page",
        "cross_page_sentence",
        "heading_dependent",
    ]
    counts_by_cat = {c: 0 for c in categories}
    for q in questions:
        counts_by_cat[q.category] += 1

    for cat, count in counts_by_cat.items():
        if count < 5:
            errors.append(f"'{cat}' kategorisinde en az 5 soru gerekli, sadece {count} bulundu.")

    # Dokümanların ve evidence metinlerinin varlığını doğrula
    from app.rag.ingestion.pdf.loader import PDFLoader

    loader = PDFLoader()
    doc_cache: dict[str, str] = {}

    for q in questions:
        doc_path = docs_dir / q.doc
        if not doc_path.is_file():
            errors.append(f"[{q.id}] Doküman bulunamadı: {doc_path}")
            continue

        if q.doc not in doc_cache:
            parsed = loader.load(doc_path)
            full_text = " ".join(e.text for e in parsed.elements)
            doc_cache[q.doc] = normalize_for_match(full_text)

        norm_doc = doc_cache[q.doc]
        for ev in q.evidence:
            norm_ev = normalize_for_match(ev)
            if norm_ev not in norm_doc:
                errors.append(
                    f"[{q.id}] Kanıt metni dokümanda bulunamadı: '{ev[:50]}...'"
                )

    is_valid = len(errors) == 0
    return is_valid, errors


def main():
    parser = argparse.ArgumentParser(description="Golden Set Doğrulama Aracı")
    parser.add_argument(
        "--validate", action="store_true", help="eval/chunking/golden_set.json dosyasını doğrula"
    )
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[4]
    json_path = root_dir / "eval" / "chunking" / "golden_set.json"
    docs_dir = root_dir / "eval" / "chunking" / "docs"

    if args.validate:
        print(f"Golden set doğrulanıyor: {json_path}")
        print(f"Doküman dizini: {docs_dir}")
        is_valid, errors = validate_golden_set(json_path, docs_dir)
        if is_valid:
            questions = load_golden_set(json_path)
            print(f"BAŞARILI: {len(questions)} soru eksiksiz ve geçerli!")
        else:
            print("HATALAR BULUNDU:")
            for err in errors:
                print(f"  - {err}")
            exit(1)


if __name__ == "__main__":
    main()
