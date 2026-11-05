"""BM25 tabanlı Qdrant sparse vektör kodlayıcısı (SparseEncoder).

Bu modül, doğal dildeki metinleri Qdrant veritabanının anlayacağı "Sparse Vektör"
formatına dönüştürür. Çıktı olarak iki paralel liste döner:
  1. indices (list[int]): Kelimelerin tekil tamsayı (uint32) kimlikleri.
  2. values (list[float]): Her kelimenin BM25 önem/ağırlık puanları.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

from app.rag.evaluation.chunking.dataset import normalize_for_match


def token_to_index(token: str) -> int:
    """Tek bir kelimeyi (token) kararlı bir uint32 tamsayı indeksine dönüştürür.

    Python'ın yerleşik `hash()` fonksiyonu her çalıştırmada rastgele bir seed
    (PYTHONHASHSEED) aldığı için kullanılmaz. Onun yerine 4 baytlık (32 bit)
    blake2b karma algoritması kullanılır. Bu sayede dünyanın her yerinde ve her
    süreçte aynı kelime her zaman birebir aynı tamsayıyı üretir.

    Örnek Girdi:
        token = "iade"

    İşlem Adımları:
        1. "iade" UTF-8 baytlarına çevrilir -> b'iade'
        2. blake2b ile 4 baytlık digest alınır -> b'\\xfa\\x91\\xae\\xe1'
        3. Baytlar little-endian uint32 tamsayıya çevrilir -> 3787056810

    Örnek Çıktı / Dönen Değer:
        3787056810 (0 ile 4.294.967.295 arasında pozitif bir int)
    """
    # 1. Metni UTF-8 baytlarına çevirip 4 baytlık (uint32) hash üret
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()

    # 2. Baytları unsigned 32-bit integer'a (pozitif tamsayı) çevir
    result_index: int = int.from_bytes(digest, byteorder="little", signed=False)

    return result_index  # Örnek dönüş: 3787056810


class SparseEncoder:
    """Doküman ve sorgu metinlerini BM25 ağırlıklı Qdrant sparse vektörlerine dönüştürür.

    Qdrant sunucusu sparse vektörlerde kelimelerin nadirlik (IDF) hesaplamasını
    kendi içinde otomatik üstlenir (Modifier.IDF).
    Bu sınıf ise:
      - Doküman tarafında: Kelime frekansı (TF) ve doküman uzunluk cezasını hesaplar.
      - Sorgu tarafında: Arama kelimelerine standart 1.0 ağırlık atar.
    """

    def __init__(
        self,
        k1: float = 1.2,
        b: float = 0.75,
        avgdl: float = 256.0,
        use_stemming: bool = False,
    ) -> None:
        """SparseEncoder parametreleri.

        Args:
            k1: Kelime sıklığı doyum katsayısı (varsayılan: 1.2).
            b: Doküman uzunluğu ceza katsayısı (0.0: ceza yok, 1.0: tam ceza, varsayılan: 0.75).
            avgdl: Ortalama doküman uzunluğu sabiti (Karar 3: Korpus bağımsız 256.0 token).
            use_stemming: True ise kelimelerin ilk 5 karakteri kök olarak alınır.
        """
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
        """Metni Türkçe-duyarlı temizler ve kelime listesine ayırır.

        Örnek Girdi:
            text = "Müşterinin İADE hakkı 14 gündür."

        İşlem Adımları:
            1. normalize_for_match: Türkçe büyük İ/I harfleri i/ı yapılır, küçük harfe indirgenir.
               -> "müşterinin iade hakkı 14 gündür."
            2. re.findall(r"\\w+"): Noktalama işaretleri atılır, sadece kelimeler toplanır.
            3. (Opsiyonel) Stemming açıksa 5 karakterden uzun kelimeler budanır.

        Örnek Çıktı / Dönen Değer:
            ["müşterinin", "iade", "hakkı", "14", "gündür"]
        """
        norm = normalize_for_match(text)
        words = re.findall(r"\w+", norm)
        if self.use_stemming:
            # 5 karakterden uzun kelimelerin ilk 5 karakterini kök olarak al
            return [w[:5] if len(w) > 5 else w for w in words]

        return words  # Örnek dönüş: ["müşteri", "iade", "talebi"]

    def encode_document(self, text: str) -> tuple[list[int], list[float]]:
        """Doküman metnini BM25 TF ağırlıklı sparse vektörüne dönüştürür.

        Örnek Girdi:
            text = "İade talebi ve iade şartları"

        İşlem Adımları:
            1. Kelimeler ayrılır -> ["iade", "talebi", "ve", "iade", "şartları"] (doc_len = 5)
            2. Kelime frekansları (TF) sayılır -> {"iade": 2, "talebi": 1, "ve": 1, "şartları": 1}
            3. BM25 formülü ile her kelimenin ağırlığı hesaplanır:
               weight = tf * (k1 + 1) / (tf + k1 * (1 - b + b * (doc_len / avgdl)))
            4. Kelimeler token_to_index ile uint32 sayıya çevrilir.
            5. Qdrant kuralı gereğince indeksler küçükten büyüğe sıralanır.

        Örnek Çıktı / Dönen Değer (tuple[list[int], list[float]]):
            (
                [691892811, 1420583921, 2849103940, 3787056810],  # Sıralı indeksler
                [0.984123,  0.984123,   0.984123,   1.624510]    # BM25 ağırlıkları ("iade" 2 kez geçtiği için 1.62)
            )
        """
        tokens = self.tokenize(text)
        # Metin boş veya sadece noktalama işaretlerinden oluşuyorsa boş vektör dön
        if not tokens:
            return [], []  # Boş metin için: ([], [])

        doc_len = len(tokens)
        counts = Counter(tokens)

        # Karar 3 Formülü: tf * (k1 + 1) / (tf + k1 * (1 - b + b * len / avgdl))
        index_weights: dict[int, float] = {}
        for token, tf in counts.items():
            idx = token_to_index(token)
            denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avgdl))
            weight = (tf * (self.k1 + 1.0)) / denom if denom > 0 else 0.0

            # Olası hash çakışmasında ağırlıkları topla (Qdrant yinelenen aynı indeksi kabul etmez)
            index_weights[idx] = index_weights.get(idx, 0.0) + weight

        # Qdrant gereksinimi: İndeksler kesinlikle küçükten büyüğe sıralı (sorted) olmalıdır
        sorted_items = sorted(index_weights.items(), key=lambda item: item[0])

        indices: list[int] = [item[0] for item in sorted_items]
        values: list[float] = [round(item[1], 6) for item in sorted_items]

        # İki paralel liste halinde sparse vektörü döndür: (indices, values)
        # Örnek: ([1420583, 3787056], [0.984123, 1.624510])
        return indices, values

    def encode_query(self, text: str) -> tuple[list[int], list[float]]:
        """Kullanıcının arama sorgusunu sparse vektörüne dönüştürür.

        Arama sorgusunda doküman uzunluğu cezası veya TF hesabı yapılmaz.
        Sorguda geçen her benzersiz kelimenin başlangıç ağırlığı standart 1.0'dır.

        Örnek Girdi:
            text = "kargo takip"

        İşlem Adımları:
            1. Kelimeler ayrılır -> ["kargo", "takip"]
            2. Her kelimenin uint32 indeksi bulunur.
            3. Her birine 1.0 ağırlığı atanır.
            4. İndeksler küçükten büyüğe sıralanır.

        Örnek Çıktı / Dönen Değer (tuple[list[int], list[float]]):
            (
                [941029412, 3819204819],  # "kargo" ve "takip" kelimelerinin uint32 indeksleri
                [1.0, 1.0]                # Sorgu ağırlıkları
            )
        """
        tokens = self.tokenize(text)
        if not tokens:
            return [], []  # Boş sorgu için: ([], [])

        counts = Counter(tokens)
        index_weights: dict[int, float] = {}
        for token in counts.keys():
            idx = token_to_index(token)
            # Karar 3: Sorgu tarafında her benzersiz token ağırlığı 1.0'dır
            # (Eğer hash çakışması olursa ağırlıklar toplanır: 1.0 + 1.0 = 2.0)
            index_weights[idx] = index_weights.get(idx, 0.0) + 1.0

        # Qdrant gereksinimi: İndeksleri sırala
        sorted_items = sorted(index_weights.items(), key=lambda item: item[0])

        indices: list[int] = [item[0] for item in sorted_items]
        values: list[float] = [round(item[1], 6) for item in sorted_items]

        # Sıralı indeksler ve 1.0 ağırlıklarını tuple olarak döndür
        # Örnek: ([941029412, 3819204819], [1.0, 1.0])
        return indices, values
