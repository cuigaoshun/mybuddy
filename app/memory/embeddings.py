from __future__ import annotations

from pathlib import Path
from typing import Protocol

EMBEDDING_MODEL_NAME = "BAAI/bge-base-zh-v1.5"
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_EMBEDDING_MODEL_PATH = PROJECT_ROOT / "model" / "baai"


class EmbeddingProvider(Protocol):
    def embed_document(self, text: str) -> list[float]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        from sentence_transformers import SentenceTransformer

        resolved_model_path = _resolve_model_path(model_name)
        self._model = SentenceTransformer(resolved_model_path)
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


def _resolve_model_path(model_name: str) -> str:
    # 优先使用仓库内置模型目录，避免 IDE/脚本因工作目录不同找不到相对路径。
    if LOCAL_EMBEDDING_MODEL_PATH.exists():
        return str(LOCAL_EMBEDDING_MODEL_PATH)

    candidate_path = Path(model_name)
    if candidate_path.exists():
        return str(candidate_path.resolve())

    # 本地目录不存在时，回退到传入的模型名，允许走 HuggingFace 仓库名加载。
    return model_name
