import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.tools.base_tool import tool_registry


@dataclass(frozen=True)
class KnowledgeDocument:
    doc_id: str
    category: str
    title: str
    content: str
    tags: tuple[str, ...]


DEFAULT_KNOWLEDGE_BASE: list[KnowledgeDocument] = [
    KnowledgeDocument(
        doc_id="POL-HYGIENE-01",
        category="RETURN_POLICY",
        title="Hijyen Ürünleri ve Kulak İçi Kulaklık İade Politikası",
        content=(
            "Mesafeli Sözleşmeler Yönetmeliği Madde 15/1-ç uyarınca; ambalajı, bant, mühür veya paketi "
            "açılmış olan kulak içi kulaklıklar, kişisel bakım ürünleri ve iç giyim ürünleri sağlık ve "
            "hijyen açısından iadeye uygun olmadığından standart 14 günlük cayma hakkı kapsamında "
            "iade edilemez. Ancak üründe teknik bir arıza veya üretim hatası bulunması durumunda "
            "yetkili servis değişim/iade raporu ile ücretsiz değişim veya para iadesi yapılır. "
            "Ergonomik uyum sorunlarında müşterilerimize ücretsiz farklı boy silikon kulaklık ucu kiti gönderilmektedir."
        ),
        tags=("kulaklık", "kulak içi", "hijyen", "ambalaj", "açılmış", "iade", "cayma hakkı", "yetkili servis"),
    ),
    KnowledgeDocument(
        doc_id="POL-PRICEMATCH-02",
        category="PRICE_POLICY",
        title="48 Saatlik Fiyat Koruma Garantisi (Price Match Guarantee)",
        content=(
            "Commerce Platform Fiyat Koruma Garantisi kapsamında; satın aldığınız bir ürünün mağaza "
            "liste fiyatı sipariş tarihinden itibaren 48 saat içerisinde düşerse, aradaki fiyat farkı "
            "hiçbir kesinti yapılmadan doğrudan alışveriş cüzdanınıza veya ödeme yaptığınız kredi kartına iade edilir."
        ),
        tags=("fiyat farkı", "indirim", "48 saat", "ucuzlamış", "fiyat düştü", "fiyat koruma", "iade"),
    ),
    KnowledgeDocument(
        doc_id="POL-DAMAGE-03",
        category="SHIPPING_DAMAGE_POLICY",
        title="Kargoda Hasarlı veya Kırık Ürün Anında Değişim Politikası",
        content=(
            "Kargo teslimatında kırık, çatlak veya hasarlı çıkan ürünlerin fotoğrafını sohbet ekranından "
            "yüklediğinizde Multimodal AI sistemimiz görseli inceler. Hasar doğrulandığında kargo tutanağı "
            "beklenmeksizin anında ücretsiz Yurtiçi Kargo iade kodu (#YRT) üretilir ve ürün kargoya "
            "teslim edildiği anda yeni ürün adresinize sevk edilir."
        ),
        tags=("kırık", "hasarlı", "çatlak", "fincan", "kargo hasar", "fotoğraf", "ücretsiz iade kodu"),
    ),
    KnowledgeDocument(
        doc_id="CAT-PLANTS-04",
        category="SEMANTIC_PRODUCT_GUIDE",
        title="Evcil Hayvan Dostu (Kediye Zararsız) ve Az Işık İsteyen Ev Bitkileri",
        content=(
            "Kediler ve köpekler için tamamen güvenli (toksik olmayan / zehirsiz / pet-friendly) ve "
            "karanlık veya az güneş alan odalarda solmadan rahatça büyüyen iki ideal iç mekan bitkimiz vardır: "
            "1) Calathea Medallion (Dua Çiçeği) [SKU: SKU-PLANT-CALATHEA] - Gölgeye dayanıklı, kedi dostu. "
            "2) Areka Palmiyesi (Chrysalidocarpus Lutescens) [SKU: SKU-PLANT-AREKA] - Toksik değildir, havayı temizler. "
            "Uyarı: Monstera Deliciosa ve الزامي Paşa Kılıcı (Sansevieria) evcil hayvanlar tarafından çiğnendiğinde "
            "mide tahrişine yol açabilir; kedili evler için Calathea Medallion ve Areka Palmiyesi önerilir."
        ),
        tags=("kedi", "evcil hayvan", "zarar vermeyen", "zehirsiz", "toksik olmayan", "karanlık oda", "az ışık", "bitki", "solmayacak", "calathea", "areka"),
    ),
    KnowledgeDocument(
        doc_id="CAT-HARDWARE-05",
        category="SEMANTIC_PRODUCT_GUIDE",
        title="Bilgisayar Donanım, Anakart, İşlemci ve DDR4/DDR5 RAM Uyumluluk Rehberi",
        content=(
            "Anakart, işlemci (CPU) ve RAM seçerken soket tipi ve bellek nesli birebir eşleşmelidir: "
            "- AMD AM4 soket anakartlar (B450, B550, X570) yalnızca DDR4 RAM destekler; DDR5 RAM takılamaz. "
            "- AMD AM5 soket anakartlar (B650, X670) yalnızca DDR5 RAM ve Ryzen 7000/9000 işlemcileri destekler. "
            "- Intel LGA1700 anakartların DDR4 ve DDR5 sürümleri ayrıdır; anakartın RAM nesli ile seçilen RAM aynı olmalıdır."
        ),
        tags=("anakart", "ram", "ddr4", "ddr5", "işlemci", "uyumluluk", "am4", "am5", "lga1700", "soket"),
    ),
]


class RAGEngine:
    """
    Lightweight vector embedding & semantic retrieval engine using character n-gram
    and token hashing with NumPy cosine similarity.
    """

    def __init__(
        self,
        documents: list[KnowledgeDocument] | None = None,
        vector_dim: int = 512,
    ) -> None:
        self.documents = list(documents) if documents is not None else list(DEFAULT_KNOWLEDGE_BASE)
        self.vector_dim = vector_dim
        self._doc_matrix = self._build_index(self.documents)

    def _embed_text(self, text: str) -> np.ndarray:
        vec = np.zeros(self.vector_dim, dtype=np.float32)
        normalized = re.sub(r"[^\w\sğüşıöçĞÜŞİÖÇ]", " ", text.lower())
        tokens = [tok for tok in normalized.split() if len(tok) >= 2]

        for token in tokens:
            # Token hash + 3-char prefix/trigram hashes for Turkish morphological suffixes
            features = [token]
            if len(token) >= 4:
                features.append(token[:4])
                features.append(token[:5])
            for i in range(len(token) - 2):
                features.append(token[i : i + 3])

            for feat in features:
                idx = hash(feat) % self.vector_dim
                vec[idx] += 1.0

        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec /= norm
        return vec

    def _build_index(self, docs: list[KnowledgeDocument]) -> np.ndarray:
        if not docs:
            return np.zeros((0, self.vector_dim), dtype=np.float32)
        rows = []
        for doc in docs:
            full_text = f"{doc.title} {' '.join(doc.tags)} {' '.join(doc.tags)} {doc.content}"
            rows.append(self._embed_text(full_text))
        return np.vstack(rows)

    def search(self, query: str, top_k: int = 2, min_score: float = 0.08) -> list[dict[str, Any]]:
        if not query or not self.documents:
            return []
        q_vec = self._embed_text(query)
        scores = np.dot(self._doc_matrix, q_vec)
        ranked_indices = np.argsort(scores)[::-1][:top_k]

        results: list[dict[str, Any]] = []
        for idx in ranked_indices:
            score = float(scores[idx])
            if score >= min_score:
                doc = self.documents[int(idx)]
                results.append(
                    {
                        "docId": doc.doc_id,
                        "category": doc.category,
                        "title": doc.title,
                        "content": doc.content,
                        "similarityScore": round(score, 4),
                    }
                )
        return results


rag_engine = RAGEngine()


@tool_registry.register(
    name="search_policy_and_product_knowledge",
    description=(
        "Scenario C.1 & D.2: Searches the semantic RAG vector knowledge base for company return policies "
        "(hygiene rules for opened earbuds, 48h price match, damaged cargo) and semantic product guides "
        "(e.g. pet-friendly low-light houseplants, hardware compatibility rules)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language question or semantic search query",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of top relevant knowledge chunks to retrieve (default 2)",
            },
        },
        "required": ["query"],
    },
)
async def search_policy_and_product_knowledge(query: str, top_k: int = 2) -> dict[str, Any]:
    matches = rag_engine.search(query=query, top_k=max(1, min(top_k, 5)))
    return {
        "query": query,
        "resultCount": len(matches),
        "documents": matches,
    }
