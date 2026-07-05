from __future__ import annotations

from typing import Protocol

EMBEDDING_MODEL_NAME = "BAAI/bge-base-zh-v1.5"


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> list[float]:
        ...


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        from sentence_transformers import SentenceTransformer
        self._model =  SentenceTransformer("./model/baai")

    def embed_text(self, text: str) -> list[float]:
        embedding = self._model.encode(text, normalize_embeddings=True)
        if hasattr(embedding, "tolist"):
            return [float(value) for value in embedding.tolist()]
        return [float(value) for value in embedding]
