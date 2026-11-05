"""SparseEncoder için birim testleri."""

import json
import os
import subprocess
import sys
import pytest
from app.rag.vectorstore.sparse import SparseEncoder, token_to_index


def test_token_to_index_uint32_range():
    """token_to_index sonucu 0 ile 2^32 - 1 arasında geçerli bir uint32 olmalıdır."""
    idx = token_to_index("siparis")
    assert isinstance(idx, int)
    assert 0 <= idx < 2**32


def test_deterministic_across_processes():
    """Farklı PYTHONHASHSEED değerleri ile çalışan süreçlerde bile aynı indeksler üretilmelidir."""
    script = (
        "import json\n"
        "from app.rag.vectorstore.sparse import SparseEncoder\n"
        "enc = SparseEncoder()\n"
        "ind, val = enc.encode_document('Müşteri iade ve cayma hakkı süresi 14 gündür.')\n"
        "print(json.dumps({'indices': ind, 'values': val}))\n"
    )

    env1 = os.environ.copy()
    env1["PYTHONHASHSEED"] = "0"
    res1 = subprocess.check_output([sys.executable, "-c", script], env=env1, text=True)
    out1 = json.loads(res1.strip())

    env2 = os.environ.copy()
    env2["PYTHONHASHSEED"] = "99999"
    res2 = subprocess.check_output([sys.executable, "-c", script], env=env2, text=True)
    out2 = json.loads(res2.strip())

    assert out1["indices"] == out2["indices"]
    assert out1["values"] == out2["values"]


def test_tf_weighting():
    """Daha sık geçen kelime (yüksek TF) daha yüksek BM25 ağırlığı almalıdır."""
    enc = SparseEncoder()
    # "iade" 1 kez geçiyor
    ind1, val1 = enc.encode_document("iade")
    # "iade" 3 kez geçiyor
    ind2, val2 = enc.encode_document("iade iade iade")

    assert ind1 == ind2  # İndeks aynı kelime için aynıdır
    assert val2[0] > val1[0]  # TF=3 olanın ağırlığı TF=1 olandan büyüktür


def test_doc_length_penalty():
    """Aynı TF'ye sahip kelime, çok daha uzun dokümanda daha düşük ağırlık almalıdır (uzunluk cezası)."""
    enc = SparseEncoder(avgdl=256.0)
    # Kısa dokümanda "kargo"
    short_doc = "hızlı kargo teslimatı"
    # Uzun dokümanda "kargo" (araya çok sayıda dolgu kelimesi eklenmiş)
    long_doc = "hızlı kargo teslimatı " + " ".join(["kelime"] * 100)

    _, short_vals = enc.encode_document(short_doc)
    _, long_vals = enc.encode_document(long_doc)

    kargo_idx = token_to_index("kargo")
    enc_short_map = dict(zip(*enc.encode_document(short_doc)))
    enc_long_map = dict(zip(*enc.encode_document(long_doc)))

    assert enc_short_map[kargo_idx] > enc_long_map[kargo_idx]


def test_indices_strictly_sorted_and_unique():
    """Dönen indeksler kesinlikle küçükten büyüğe sıralı ve benzersiz olmalıdır."""
    enc = SparseEncoder()
    text = "Bir e-ticaret platformunda stok ve sipariş yönetimi, iade, kargo ve ödeme akışları."
    indices, values = enc.encode_document(text)

    assert len(indices) == len(values)
    assert len(indices) > 0

    # Kesin artan sıra kontrolü (her eleman bir öncekinden kesinlikle büyük olmalı)
    for i in range(len(indices) - 1):
        assert indices[i] < indices[i + 1]


def test_empty_and_whitespace():
    """Boş, sadece boşluk veya sadece noktalama içeren metinler hata vermeden boş liste dönmelidir."""
    enc = SparseEncoder()
    assert enc.encode_document("") == ([], [])
    assert enc.encode_document("   \n\t  ") == ([], [])
    assert enc.encode_document("!.,;:?") == ([], [])

    assert enc.encode_query("") == ([], [])
    assert enc.encode_query("   ") == ([], [])


def test_turkish_normalization():
    """Büyük/küçük İ ve I harfleri doğru Türkçe normalizasyonla aynı indekse düşmelidir."""
    enc = SparseEncoder()
    # Dotted 'İ' / 'i'
    ind1, _ = enc.encode_document("İADE")
    ind2, _ = enc.encode_document("iade")
    ind3, _ = enc.encode_document("İade")
    assert ind1 == ind2 == ind3

    # Dotless 'I' / 'ı'
    ind_isik1, _ = enc.encode_document("IŞIK")
    ind_isik2, _ = enc.encode_document("ışık")
    ind_isik3, _ = enc.encode_document("Işık")
    assert ind_isik1 == ind_isik2 == ind_isik3


def test_encode_query_weights():
    """Sorgudaki her benzersiz kelimenin ağırlığı 1.0 olmalıdır."""
    enc = SparseEncoder()
    indices, values = enc.encode_query("iade süresi kaç gün")
    assert len(indices) == 4
    assert values == [1.0, 1.0, 1.0, 1.0]

    # Tekrarlanan kelime sorguda sadece bir kez 1.0 olarak alınır
    indices_repeat, values_repeat = enc.encode_query("iade iade iade")
    assert len(indices_repeat) == 1
    assert values_repeat == [1.0]


def test_invalid_parameters():
    """Geçersiz parametreler ValueError fırlatmalıdır."""
    with pytest.raises(ValueError, match="k1 negatif olamaz"):
        SparseEncoder(k1=-0.1)

    with pytest.raises(ValueError, match="b \\[0.0, 1.0\\]"):
        SparseEncoder(b=1.5)

    with pytest.raises(ValueError, match="avgdl sıfırdan büyük"):
        SparseEncoder(avgdl=0)
