import pytest

from app.rag.embedding.batching import (
    batched,
    is_non_retryable_error,
    validate_non_empty_texts,
    with_retry,
)


def test_batched_splits_correctly():
    items = [1, 2, 3, 4, 5]
    batches = list(batched(items, 2))
    assert batches == [[1, 2], [3, 4], [5]]

    assert list(batched([], 2)) == []
    assert list(batched([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]

    with pytest.raises(ValueError):
        list(batched([1], 0))


def test_validate_non_empty_texts():
    validate_non_empty_texts(["merhaba", "dunya"])

    with pytest.raises(ValueError, match="index 0"):
        validate_non_empty_texts(["", "dunya"])

    with pytest.raises(ValueError, match="index 1"):
        validate_non_empty_texts(["merhaba", "   "])


class DummyHttpError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


def test_is_non_retryable_error():
    assert is_non_retryable_error(DummyHttpError(401)) is True
    assert is_non_retryable_error(DummyHttpError(400)) is True
    assert is_non_retryable_error(DummyHttpError(403)) is True

    # 429 ve 5xx tekrar denenebilir
    assert is_non_retryable_error(DummyHttpError(429)) is False
    assert is_non_retryable_error(DummyHttpError(500)) is False
    assert is_non_retryable_error(DummyHttpError(503)) is False
    assert is_non_retryable_error(ConnectionError("network down")) is False


def test_with_retry_succeeds_immediately():
    calls = 0

    def fn():
        nonlocal calls
        calls += 1
        return "success"

    res = with_retry(fn)
    assert res == "success"
    assert calls == 1


def test_with_retry_transient_error_then_success():
    calls = 0
    sleeps = []

    def mock_sleep(d):
        sleeps.append(d)

    def fn():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise DummyHttpError(503)
        return "recovered"

    res = with_retry(fn, max_attempts=5, base_delay=0.1, sleep_fn=mock_sleep)
    assert res == "recovered"
    assert calls == 3
    assert len(sleeps) == 2


def test_with_retry_non_retryable_fails_fast():
    calls = 0
    sleeps = []

    def fn():
        nonlocal calls
        calls += 1
        raise DummyHttpError(401)  # Unauthorized

    with pytest.raises(DummyHttpError):
        with_retry(fn, max_attempts=5, sleep_fn=lambda d: sleeps.append(d))

    # 401 hatasında ikinci deneme yapılmadan hemen fail olmalı
    assert calls == 1
    assert len(sleeps) == 0


def test_with_retry_exhausts_attempts():
    calls = 0

    def fn():
        nonlocal calls
        calls += 1
        raise DummyHttpError(500)

    with pytest.raises(DummyHttpError):
        with_retry(fn, max_attempts=3, sleep_fn=lambda _: None)

    assert calls == 3
