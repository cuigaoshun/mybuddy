from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed_document(self, text: str) -> list[float]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...
