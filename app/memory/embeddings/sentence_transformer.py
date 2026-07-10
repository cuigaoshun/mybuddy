from __future__ import annotations

from pathlib import Path
from typing import Final

from app.memory.embeddings.base import EmbeddingProvider

EMBEDDING_MODEL_NAME: Final[str] = "BAAI/bge-base-zh-v1.5"
QUERY_INSTRUCTION: Final[str] = "为这个句子生成表示以用于检索相关文章："
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
LOCAL_EMBEDDING_MODEL_PATH: Final[Path] = PROJECT_ROOT / "model" / "baai"


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        from sentence_transformers import SentenceTransformer

        resolved_model_path = _resolve_model_path(model_name)
        self._model = SentenceTransformer(resolved_model_path)
        self._model_name = model_name

    def embed_document(self, text: str) -> list[float]:
        return self._encode(text)

    def embed_query(self, text: str) -> list[float]:
        normalized_text = text.strip()
        if not normalized_text:
            return self._encode(normalized_text)
        return self._encode(f"{QUERY_INSTRUCTION}{normalized_text}")

    def _encode(self, text: str) -> list[float]:
        embedding = self._model.encode(text, normalize_embeddings=True)
        if hasattr(embedding, "tolist"):
            return [float(value) for value in embedding.tolist()]
        return [float(value) for value in embedding]


def _resolve_model_path(model_name: str) -> str:
    if LOCAL_EMBEDDING_MODEL_PATH.exists():
        return str(LOCAL_EMBEDDING_MODEL_PATH)

    candidate_path = Path(model_name)
    if candidate_path.exists():
        return str(candidate_path.resolve())

    return model_name
