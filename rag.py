"""BM25 + Semantic 하이브리드 법령 조문 검색 (Reciprocal Rank Fusion)"""
import re
import json
from pathlib import Path

import numpy as np

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    raise ImportError("pip install rank-bm25")


def _tokenize(text: str) -> list[str]:
    words = re.findall(r'[가-힣]+|[0-9]+', text)
    tokens = list(words)
    for w in words:
        if len(w) >= 2:
            for i in range(len(w) - 1):
                tokens.append(w[i:i + 2])
    return tokens


class LawRetriever:
    def __init__(self, chunks_path: Path, embeddings_path: Path = None, voyage_api_key: str = ""):
        # BM25 로드
        with open(chunks_path, encoding="utf-8") as f:
            self.chunks = json.load(f)
        print(f"  BM25 인덱싱 중... ({len(self.chunks)}개 조문)")
        corpus = [_tokenize(c["text"]) for c in self.chunks]
        self.bm25 = BM25Okapi(corpus)

        # Semantic 로드 (선택)
        self.embeddings = None
        self.vo = None
        if embeddings_path and embeddings_path.exists() and voyage_api_key:
            import voyageai
            self.embeddings = np.load(embeddings_path)          # (N, 512)
            # L2 정규화 (코사인 유사도 = 내적)
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
            self.embeddings = self.embeddings / (norms + 1e-8)
            self.vo = voyageai.Client(api_key=voyage_api_key)
            print(f"  Semantic 검색 활성화 (voyage-3-lite, {self.embeddings.shape})")
        else:
            print("  BM25 전용 모드 (임베딩 없음)")

    def retrieve(self, query: str, top_k: int = 25) -> str:
        tokens = _tokenize(query)
        bm25_scores = self.bm25.get_scores(tokens) if tokens else np.zeros(len(self.chunks))

        if self.embeddings is not None and self.vo is not None:
            # Semantic 점수
            q_emb = np.array(
                self.vo.embed([query], model="voyage-3-lite", input_type="query").embeddings[0],
                dtype=np.float32,
            )
            q_emb /= (np.linalg.norm(q_emb) + 1e-8)
            sem_scores = self.embeddings @ q_emb  # cosine similarity

            # Reciprocal Rank Fusion (RRF)
            k = 60
            rrf = np.zeros(len(self.chunks))
            for rank, idx in enumerate(np.argsort(-bm25_scores)):
                rrf[idx] += 1.0 / (k + rank + 1)
            for rank, idx in enumerate(np.argsort(-sem_scores)):
                rrf[idx] += 1.0 / (k + rank + 1)
            top_indices = np.argsort(-rrf)[:top_k]
        else:
            # BM25 전용
            top_indices = np.argsort(-bm25_scores)[:top_k]

        results = []
        for i in top_indices:
            c = self.chunks[i]
            results.append(f"[{c['law']} {c['article']}]\n{c['text']}")

        return "\n\n".join(results)
