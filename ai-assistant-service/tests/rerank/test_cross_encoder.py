import concurrent.futures
import sys
import types
import pytest
from app.rag.rerank.cross_encoder import CrossEncoderReranker
from app.rag.rerank.models import RerankError


class MockCrossEncoder:
    init_count = 0

    def __init__(self, model_name: str, max_length: int = 512, device: str | None = None) -> None:
        MockCrossEncoder.init_count += 1
        self.model_name = model_name
        self.max_length = max_length
        self.device = device
        self.last_pairs = None

    def predict(self, pairs: list[list[str]], batch_size: int = 16) -> list[float]:
        self.last_pairs = pairs
        # Eğer çiftte "iyi" geçiyorsa yüksek skor, yoksa düşük skor dönsün
        scores = []
        for query, doc in pairs:
            if "iyi" in doc:
                scores.append(0.95)
            elif "orta" in doc:
                scores.append(0.50)
            else:
                scores.append(0.10)
        return scores


@pytest.fixture(autouse=True)
def reset_mock_state():
    MockCrossEncoder.init_count = 0


def test_cross_encoder_lazy_loading(monkeypatch):
    mock_module = types.ModuleType("sentence_transformers")
    mock_module.CrossEncoder = MockCrossEncoder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", mock_module)

    reranker = CrossEncoderReranker(model_name="test-model")
    # Kurucu çağrısında model yüklenmemelidir
    assert MockCrossEncoder.init_count == 0
    assert reranker._model is None

    # İlk rerank çağrısı
    results = reranker.rerank("soru", ["kötü doc", "iyi doc"])
    assert MockCrossEncoder.init_count == 1
    assert len(results) == 2
    assert results[0].index == 1  # "iyi doc" birinci
    assert results[0].score == 0.95

    # İkinci rerank çağrısında tekrar model yüklenmemelidir
    reranker.rerank("soru 2", ["orta doc"])
    assert MockCrossEncoder.init_count == 1


def test_cross_encoder_pairs_and_sorting(monkeypatch):
    class CustomMockCrossEncoder:
        def __init__(self, *args, **kwargs):
            pass

        def predict(self, pairs, batch_size=16):
            # doc0: 0.5, doc1: 0.9, doc2: 0.5
            return [0.5, 0.9, 0.5]

    mock_module = types.ModuleType("sentence_transformers")
    mock_module.CrossEncoder = CustomMockCrossEncoder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", mock_module)

    reranker = CrossEncoderReranker()
    docs = ["doc0", "doc1", "doc2"]
    results = reranker.rerank("arama sorgusu", docs)

    # doc1 en yüksek (0.9), doc0 ve doc2 eşit (0.5) olduğu için orijinal sıra (0 sonra 2) korunmalı
    assert results[0].index == 1
    assert results[0].score == 0.9
    assert results[1].index == 0
    assert results[1].score == 0.5
    assert results[2].index == 2
    assert results[2].score == 0.5


def test_cross_encoder_empty_documents():
    reranker = CrossEncoderReranker()
    results = reranker.rerank("soru", [])
    assert results == []


def test_cross_encoder_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)

    reranker = CrossEncoderReranker()
    with pytest.raises(RerankError, match="sentence-transformers kütüphanesi kurulu değil"):
        reranker.rerank("soru", ["doc1"])


def test_cross_encoder_predict_failure(monkeypatch):
    class BrokenMockCrossEncoder:
        def __init__(self, *args, **kwargs):
            pass

        def predict(self, pairs, batch_size=16):
            raise RuntimeError("CUDA out of memory")

    mock_module = types.ModuleType("sentence_transformers")
    mock_module.CrossEncoder = BrokenMockCrossEncoder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", mock_module)

    reranker = CrossEncoderReranker()
    with pytest.raises(RerankError, match="CrossEncoder rerank çağrısı başarısız: RuntimeError"):
        reranker.rerank("soru", ["doc1"])


def test_cross_encoder_concurrent_threads(monkeypatch):
    mock_module = types.ModuleType("sentence_transformers")
    mock_module.CrossEncoder = MockCrossEncoder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", mock_module)

    reranker = CrossEncoderReranker()

    def worker(i: int):
        return reranker.rerank(f"soru {i}", ["kötü doc", "iyi doc"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i) for i in range(20)]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            assert len(res) == 2
            assert res[0].index == 1

    # 20 thread eşzamanlı çalışmasına rağmen model yalnızca 1 kez oluşturuldu
    assert MockCrossEncoder.init_count == 1


@pytest.mark.integration
def test_cross_encoder_real_model():
    try:
        from sentence_transformers import CrossEncoder  # noqa: F401
    except ImportError:
        pytest.skip("sentence-transformers kurulu değil, entegrasyon testi atlandı")

    reranker = CrossEncoderReranker(model_name="cross-encoder/ms-marco-TinyBERT-L-2-v2")
    docs = [
        "Bugün hava çok yağmurlu ve rüzgarlı.",
        "İade edilen ürünün bedeli 14 gün içinde kartınıza yansıtılır.",
        "Mutfak robotu kullanım kılavuzu ve garanti belgesi.",
    ]
    results = reranker.rerank("İade param ne zaman yatar?", docs)
    assert len(results) == 3
    # İade ile ilgili olan 1 numaralı doküman en üstte çıkmalı
    assert results[0].index == 1
