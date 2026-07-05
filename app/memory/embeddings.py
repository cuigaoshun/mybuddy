from __future__ import annotations

from typing import Protocol

EMBEDDING_MODEL_NAME = "BAAI/bge-base-zh-v1.5"
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class EmbeddingProvider(Protocol):
    def embed_document(self, text: str) -> list[float]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer("./model/baai")
        self._model_name = model_name

    def embed_document(self, text: str) -> list[float]:
        # BGE v1.5 官方推荐：passage/document 侧不加 query instruction。
        return self._encode(text)

    def embed_query(self, text: str) -> list[float]:
        # BGE v1.5 官方推荐：检索 query 侧加 instruction，以提升 s2p 检索效果。
        normalized_text = text.strip()
        if not normalized_text:
            return self._encode(normalized_text)
        return self._encode(f"{QUERY_INSTRUCTION}{normalized_text}")

    def _encode(self, text: str) -> list[float]:
        embedding = self._model.encode(text, normalize_embeddings=True)
        if hasattr(embedding, "tolist"):
            return [float(value) for value in embedding.tolist()]
        return [float(value) for value in embedding]
