"""BM25 tabanlı Qdrant sparse vektör kodlayıcısı (SparseEncoder)."""

from __future__ import annotations

import hashlib
import re
from collections import Counter

from app.rag.evaluation.chunking.dataset import normalize_for_match


def token_to_index(token: str) -> int:
    """Token'ı kararlı (deterministic) ve süreçler arası değişmeyen bir uint32 indekse dönüştürür.

    Python'ın dahili hash() fonksiyonu süreç başına rastgele seed (PYTHONHASHSEED)
    kullandığından Qdrant sparse indeksi için güvenle kullanılamaz.
    blake2b ile 4 baytlık (uint32) sabit karma üretilir.
    """
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, byteorder="little", signed=False)


class SparseEncoder:
    """Doküman ve sorgu metinlerini BM25 ağırlıklı Qdrant sparse vektörlerine dönüştürür.

    Qdrant sunucusu sparse vektörlerde IDF hesaplamasını üstlenir (Modifier.IDF).
    Bu sınıf doküman tarafında TF ve uzunluk cezasını (BM25 doc weight),
    sorgu tarafında ise tekil terim ağırlıklarını (1.0) üretir.
    """

    def __init__(
        self,
        k1: float = 1.2,
        b: float = 0.75,
        avgdl: float = 256.0,
        use_stemming: bool = False,
    ) -> None:
        if k1 < 0:
            raise ValueError(f"k1 negatif olamaz: {k1}")
        if not 0.0 <= b <= 1.0:
            raise ValueError(f"b [0.0, 1.0] aralığında olmalıdır: {b}")
        if avgdl <= 0:
            raise ValueError(f"avgdl sıfırdan büyük olmalıdır: {avgdl}")

        self.k1 = k1
        self.b = b
        self.avgdl = avgdl
        self.use_stemming = use_stemming

    def tokenize(self, text: str) -> list[str]:
        """Metni Türkçe-duyarlı normalizasyon ve opsiyonel prefix-stem ile kelimelere ayırır."""
        norm = normalize_for_match(text)
        words = re.findall(r"\w+", norm)
        if self.use_stemming:
            # 5 karakterden uzun kelimelerin ilk 5 karakterini kök olarak al
            return [w[:5] if len(w) > 5 else w for w in words]
        return words

    def encode_document(self, text: str) -> tuple[list[int], list[float]]:
        """Doküman metnini BM25 TF ağırlıklı (indices, values) sparse vektörüne dönüştürür.

        İndeksler sıralı ve tekildir. Çakışma durumunda ağırlıklar toplanır.
        """
        tokens = self.tokenize(text)
        if not tokens:
            return [], []

        doc_len = len(tokens)
        counts = Counter(tokens)

        # Karar 3: tf * (k1 + 1) / (tf + k1 * (1 - b + b * len / avgdl))
        index_weights: dict[int, float] = {}
        for token, tf in counts.items():
            idx = token_to_index(token)
            denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avgdl))
            weight = (tf * (self.k1 + 1.0)) / denom if denom > 0 else 0.0

            # Hash çakışması olursa ağırlıklar toplanır (Qdrant yinelenen indeksi reddeder)
            index_weights[idx] = index_weights.get(idx, 0.0) + weight

        sorted_items = sorted(index_weights.items(), key=lambda item: item[0])
        indices = [item[0] for item in sorted_items]
        values = [round(item[1], 6) for item in sorted_items]
        return indices, values

    def encode_query(self, text: str) -> tuple[list[int], list[float]]:
        """Arama sorgusunu (indices, values) sparse vektörüne dönüştürür.

        Sorgu terimlerinin ağırlığı standart 1.0'dır (çakışmada toplanır).
        """
        tokens = self.tokenize(text)
        if not tokens:
            return [], []

        counts = Counter(tokens)
        index_weights: dict[int, float] = {}
        for token in counts.keys():
            idx = token_to_index(token)
            # Karar 3: sorgu tarafında her benzersiz token ağırlığı 1.0
            index_weights[idx] = index_weights.get(idx, 0.0) + 1.0

        sorted_items = sorted(index_weights.items(), key=lambda item: item[0])
        indices = [item[0] for item in sorted_items]
        values = [round(item[1], 6) for item in sorted_items]
        return indices, values
