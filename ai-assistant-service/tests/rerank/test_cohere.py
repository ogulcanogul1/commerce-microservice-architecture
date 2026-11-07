import json
import httpx
import pytest
from app.rag.rerank.cohere import CohereReranker
from app.rag.rerank.models import RerankError


def test_cohere_missing_api_key(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "COHERE_API_KEY", "")

    with pytest.raises(ValueError, match="COHERE_API_KEY tanımlı değil"):
        CohereReranker(api_key="")


def test_cohere_successful_rerank():
    captured_request = {}

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["auth"] = request.headers.get("Authorization")
        captured_request["body"] = json.loads(request.content.decode("utf-8"))

        response_data = {
            "id": "rerank-test-123",
            "results": [
                {"index": 1, "relevance_score": 0.95},
                {"index": 0, "relevance_score": 0.20},
                {"index": 2, "relevance_score": 0.80},
            ],
        }
        return httpx.Response(200, json=response_data)

    transport = httpx.MockTransport(handle_request)
    reranker = CohereReranker(api_key="test-cohere-key", transport=transport)

    docs = ["doc0", "doc1", "doc2"]
    results = reranker.rerank("iade süresi", docs)

    # İstek doğrulaması
    assert captured_request["url"] == "https://api.cohere.com/v2/rerank"
    assert captured_request["auth"] == "Bearer test-cohere-key"
    assert captured_request["body"]["model"] == "rerank-v3.5"
    assert captured_request["body"]["query"] == "iade süresi"
    assert captured_request["body"]["documents"] == docs
    assert captured_request["body"]["top_n"] == 3

    # Sonuçlar azalan sıralı olmalı: 1 (0.95), 2 (0.80), 0 (0.20)
    assert len(results) == 3
    assert results[0].index == 1
    assert results[0].score == 0.95
    assert results[1].index == 2
    assert results[1].score == 0.80
    assert results[2].index == 0
    assert results[2].score == 0.20


def test_cohere_empty_documents():
    reranker = CohereReranker(api_key="test-key")
    results = reranker.rerank("soru", [])
    assert results == []


def test_cohere_missing_index_raises():
    def handle_request(request: httpx.Request) -> httpx.Response:
        response_data = {
            "results": [
                {"index": 1, "relevance_score": 0.95},
                # index 0 eksik!
            ]
        }
        return httpx.Response(200, json=response_data)

    transport = httpx.MockTransport(handle_request)
    reranker = CohereReranker(api_key="test-key", transport=transport)

    with pytest.raises(RerankError, match="eksik veya fazla sonuç"):
        reranker.rerank("soru", ["d0", "d1"])


def test_cohere_rate_limit_retry_success():
    attempt_count = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            return httpx.Response(429, json={"message": "Rate limit exceeded"})
        return httpx.Response(
            200, json={"results": [{"index": 0, "relevance_score": 0.9}]}
        )

    transport = httpx.MockTransport(handle_request)
    reranker = CohereReranker(api_key="test-key", transport=transport)

    results = reranker.rerank("soru", ["d0"])
    assert attempt_count == 2
    assert len(results) == 1
    assert results[0].score == 0.9


def test_cohere_rate_limit_retry_exhausted():
    attempt_count = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        return httpx.Response(429, json={"message": "Rate limit exceeded"})

    transport = httpx.MockTransport(handle_request)
    reranker = CohereReranker(api_key="test-key", transport=transport)

    with pytest.raises(RerankError, match="Cohere Rerank API sunucu hatası"):
        reranker.rerank("soru", ["d0"])

    assert attempt_count == 2


def test_cohere_client_error_fail_fast():
    attempt_count = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        return httpx.Response(401, json={"message": "Invalid API key"})

    transport = httpx.MockTransport(handle_request)
    reranker = CohereReranker(api_key="test-key", transport=transport)

    with pytest.raises(RerankError, match="Cohere Rerank API istemci hatası"):
        reranker.rerank("soru", ["d0"])

    # 401 hatasında retry yapılmamalıdır
    assert attempt_count == 1


def test_cohere_timeout_handling():
    def handle_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out")

    transport = httpx.MockTransport(handle_request)
    reranker = CohereReranker(api_key="test-key", transport=transport)

    with pytest.raises(RerankError, match="Cohere Rerank API ağ hatası"):
        reranker.rerank("soru", ["d0"])


def test_cohere_error_message_does_not_leak_secrets_or_query():
    secret_key = "secret-super-private-key-12345"
    sensitive_query = "kullanici_tc_12345678901"
    sensitive_doc = "gizli_dokuman_icerigi_ozel"

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Internal Server Error"})

    transport = httpx.MockTransport(handle_request)
    reranker = CohereReranker(api_key=secret_key, transport=transport)

    with pytest.raises(RerankError) as exc_info:
        reranker.rerank(sensitive_query, [sensitive_doc])

    err_str = str(exc_info.value)
    assert secret_key not in err_str
    assert sensitive_query not in err_str
    assert sensitive_doc not in err_str


@pytest.mark.integration
def test_cohere_real_api():
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.COHERE_API_KEY:
        pytest.skip("COHERE_API_KEY tanımlı değil, canlı entegrasyon testi atlandı")

    reranker = CohereReranker()
    docs = [
        "Bugün hava güneşli.",
        "İptal edilen siparişlerin ücret iadesi 3 iş gününde bankaya iletilir.",
        "Yeni kampanya dönemi başladı.",
    ]
    results = reranker.rerank("İptal ettiğim siparişin parası ne zaman yatar?", docs)
    assert len(results) == 3
    assert results[0].index == 1
