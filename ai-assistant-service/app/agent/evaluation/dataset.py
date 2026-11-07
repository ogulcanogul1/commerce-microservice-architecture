"""Dataset loader and validator for customer support agent evaluation.

Validates evaluation cases in eval/agent/cases.json to ensure uniqueness,
valid categories, expected reply kinds, and mandatory adversarial constraints.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_CASES_PATH = Path("eval/agent/cases.json")

VALID_CATEGORIES = {
    "order_status",
    "list_orders",
    "shipment",
    "policy",
    "cancel",
    "ticket",
    "clarify",
    "adversarial",
    "hallucination_trap",
}

ReplyKind = Literal["answer", "policy_answer", "abstained", "pending_action", "fallback"]


class AgentCase(BaseModel):
    """A single handcrafted evaluation case for the conversational agent."""

    id: str = Field(description="Unique identifier (e.g. A01)")
    message: str = Field(description="User natural language message/prompt")
    expected_tools: list[str] = Field(default_factory=list, description="Expected tools to be invoked")
    expected_args: dict[str, Any] | None = Field(default=None, description="Expected arguments or subset")
    expected_kind: ReplyKind = Field(description="Expected final AgentReply kind")
    must_contain: list[str] = Field(default_factory=list, description="Substrings that must appear in reply")
    must_not_contain: list[str] = Field(default_factory=list, description="Forbidden substrings that must not appear")
    must_not_call: list[str] = Field(default_factory=list, description="Tools strictly forbidden from being called")
    category: str = Field(description="Evaluation category")
    notes: str = Field(default="", description="Case notes and rationale")


def load_raw_cases(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSON array file from disk."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Değerlendirme veri seti dosyası bulunamadı: {p}")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"JSON liste olmalıdır, alınan: {type(data).__name__}")
    return data


def validate_agent_cases(cases: list[AgentCase]) -> None:
    """Validate semantic integrity of the loaded agent evaluation cases."""
    seen_ids: set[str] = set()

    for idx, case in enumerate(cases):
        prefix = f"Vaka #{idx + 1} ({case.id}):"

        # 1. Tekil ID
        if case.id in seen_ids:
            raise ValueError(f"{prefix} Yinelenen id: '{case.id}'")
        seen_ids.add(case.id)

        # 2. Geçerli Kategori
        if case.category not in VALID_CATEGORIES:
            raise ValueError(
                f"{prefix} Geçersiz kategori '{case.category}'. "
                f"İzin verilenler: {sorted(VALID_CATEGORIES)}"
            )

        # 3. Mesaj boş olamaz
        if not case.message.strip():
            raise ValueError(f"{prefix} 'message' alanı boş olamaz.")

        # 4. Adversarial vakalar güvenlik kuralı içermeli
        if case.category == "adversarial":
            if not case.must_not_call and not case.must_not_contain:
                raise ValueError(
                    f"{prefix} 'adversarial' kategorisindeki vakalarda "
                    f"'must_not_call' veya 'must_not_contain' alanlarından en az biri dolu olmalıdır."
                )


def load_agent_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[AgentCase]:
    """Load and validate all agent evaluation cases from specified JSON file."""
    raw_list = load_raw_cases(path)
    cases = [AgentCase.model_validate(item) for item in raw_list]
    validate_agent_cases(cases)
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent evaluation dataset validator CLI")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to agent cases JSON file",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate dataset structure and print summary",
    )
    args = parser.parse_args()

    cases = load_agent_cases(args.path)
    print(f"BAŞARILI: {len(cases)} adet değerlendirme vakası doğrulandı.")

    cat_counts: dict[str, int] = {}
    for c in cases:
        cat_counts[c.category] = cat_counts.get(c.category, 0) + 1

    print("\nKategori Dağılımı:")
    for cat, count in sorted(cat_counts.items()):
        print(f"  - {cat:20}: {count} vaka")


if __name__ == "__main__":
    main()
