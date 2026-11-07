# Reranker Karar Günlüğü (Decisions Log)

- **Corpus Durumu:** 3 PDF ≈ 8 chunk. Aday havuzu tüm corpus'u kapsayabildiği için reranker açma/kapama nihai kararı büyük corpus gelince verilecektir.
- **Varsayılan Durum:** Reranker varsayılan olarak KAPALI (`RAG_RERANK_ENABLED=False`).
- **Baseline Test Sayısı:** 471 passed, 5 deselected (pytest -m "not integration")
