from __future__ import annotations

from app.storage.models import UserMemory
from app.storage.repositories import UserMemoryRepository


class UserMemoryService:
    """用户级长期记忆读取服务。"""

    def __init__(self, repository: UserMemoryRepository) -> None:
        self._repository = repository

    def get_user_memory(self, user_id: str, im_type: str) -> UserMemory | None:
        return self._repository.get_by_user(user_id=user_id, im_type=im_type)

    def save_user_memory(self, user_memory: UserMemory) -> None:
        self._repository.save(user_memory)
