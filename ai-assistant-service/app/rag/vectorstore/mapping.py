"""Chunk ve Qdrant point/payload arasındaki dönüşüm yardımcıları."""

from __future__ import annotations

import uuid
from typing import Any

from app.rag.chunking.models import Chunk


def chunk_point_id(chunk_id: str) -> str:
    """Chunk ID'den (16 hex karakter) deterministik bir UUIDv5 üretir.

    Qdrant yalnızca standart UUID veya unsigned integer point ID'lerini kabul eder.
    Aynı chunk_id her zaman aynı UUID'yi üretir (idempotent).
    """
    if not chunk_id or not chunk_id.strip():
        raise ValueError("chunk_id boş olamaz")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id.strip()))


def chunk_to_payload(
    chunk: Chunk,
    *,
    doc_hash: str,
    embedding_model_id: str,
    ingested_at: str,
    chunk_count: int | None = None,
) -> dict[str, Any]:
    """Bir Chunk nesnesini Qdrant payload sözlüğüne dönüştürür.

    Not: 'embedding_text' payload'a yazılmaz; context_prefix ve text üzerinden
    türetildiği için diskte fazladan yer kaplaması engellenir.
    'chunk_count' ise o dokümana ait toplam chunk sayısını saklayarak
    kesintiye uğrayan yarım yazma işlemlerini tespit etmeyi sağlar.
    """
    payload = chunk.model_dump(mode="json", exclude={"embedding_text"})
    payload["doc_hash"] = doc_hash
    payload["embedding_model_id"] = embedding_model_id
    payload["ingested_at"] = ingested_at
    if chunk_count is not None:
        payload["chunk_count"] = chunk_count
    return payload


def payload_to_chunk(payload: dict[str, Any]) -> Chunk:
    """Qdrant payload sözlüğünden eksiksiz ve doğrulanmış bir Chunk nesnesi oluşturur."""
    # Qdrant'a özgü operasyonel metadata alanlarını ayıkla
    data = dict(payload)
    data.pop("doc_hash", None)
    data.pop("embedding_model_id", None)
    data.pop("ingested_at", None)
    data.pop("chunk_count", None)

    return Chunk.model_validate(data)
