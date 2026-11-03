"""Batching, retry with exponential backoff, and validation utilities for embedding calls."""

import random
import time
from typing import Callable, Iterator, Sequence, TypeVar

T = TypeVar("T")


def batched(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    """Yield successive batches of the specified size from a sequence."""
    if size < 1:
        raise ValueError("Batch size must be at least 1")
    for i in range(0, len(items), size):
        yield items[i : i + size]


def validate_non_empty_texts(texts: Sequence[str]) -> None:
    """Validate that texts sequence contains non-empty, non-whitespace strings.

    Raises ValueError if any item is empty or only whitespace.
    """
    for idx, text in enumerate(texts):
        if not text or not text.strip():
            raise ValueError(
                f"Text at index {idx} is empty or contains only whitespace"
            )


def is_non_retryable_error(exc: Exception) -> bool:
    """Determine whether an exception is a non-retryable client error (4xx except 429)."""
    # Standart HTTP durum kodlarını kontrol et
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status_code, int):
        # 429 Rate Limit hariç 4xx hataları retry edilmez (400, 401, 403, 404, 422 vs.)
        if 400 <= status_code < 500 and status_code != 429:
            return True

    # Pydantic, ValueError veya TypeError gibi kodlama/istek hataları retry edilmez
    if isinstance(exc, (ValueError, TypeError)):
        return True

    return False


def with_retry(
    fn: Callable[[], T],
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    """Execute a callable with exponential backoff and jitter.

    Retries on transient errors (429, 5xx, timeouts, network issues).
    Fails fast on permanent client errors (400, 401, etc.).
    """
    attempt = 1
    while True:
        try:
            return fn()
        except Exception as exc:
            if is_non_retryable_error(exc) or attempt >= max_attempts:
                raise

            # Exponential backoff: base_delay * 2^(attempt - 1)
            backoff = min(base_delay * (2 ** (attempt - 1)), max_delay)
            # Add full jitter (0.8x to 1.2x) to avoid thundering herd problem
            jitter = random.uniform(0.8, 1.2)
            sleep_duration = backoff * jitter

            sleep_fn(sleep_duration)
            attempt += 1
