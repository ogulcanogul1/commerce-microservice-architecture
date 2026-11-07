import pytest
from pydantic import ValidationError
from app.rag.rerank.models import RerankError, RerankResult, validate_rerank_results


def test_rerank_result_frozen():
    res = RerankResult(index=0, score=0.85)
    assert res.index == 0
    assert res.score == 0.85
    with pytest.raises(ValidationError):
        res.score = 0.99  # type: ignore[misc]


def test_validate_rerank_results_valid():
    results = [
        RerankResult(index=2, score=0.9),
        RerankResult(index=0, score=0.5),
        RerankResult(index=1, score=0.1),
    ]
    # n=3 için 0, 1, 2 var -> geçerli
    validate_rerank_results(results, 3)


def test_validate_rerank_results_empty():
    validate_rerank_results([], 0)


def test_validate_rerank_results_length_mismatch():
    results = [
        RerankResult(index=0, score=0.9),
    ]
    with pytest.raises(RerankError, match="eksik veya fazla sonuç"):
        validate_rerank_results(results, 2)


def test_validate_rerank_results_out_of_range():
    results = [
        RerankResult(index=0, score=0.9),
        RerankResult(index=2, score=0.5),  # 2 >= n (n=2)
    ]
    with pytest.raises(RerankError, match="geçersiz index"):
        validate_rerank_results(results, 2)

    results_negative = [
        RerankResult(index=-1, score=0.9),
    ]
    with pytest.raises(RerankError, match="geçersiz index"):
        validate_rerank_results(results_negative, 1)


def test_validate_rerank_results_duplicate():
    results = [
        RerankResult(index=0, score=0.9),
        RerankResult(index=0, score=0.5),
    ]
    with pytest.raises(RerankError, match="yinelenen index"):
        validate_rerank_results(results, 2)
