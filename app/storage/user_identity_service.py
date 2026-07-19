from __future__ import annotations

from app.storage.repositories import UserIdentityRepository


class UserIdentityService:
    """用户身份解析服务，负责把第三方身份收敛为系统 user_id。"""

    def __init__(self, repository: UserIdentityRepository) -> None:
        self._repository = repository

    def get_or_create_user_id(self, im_type: str, third_party_user_id: str) -> str:
        return self._repository.get_or_create_user_id(
            im_type=im_type,
            third_party_user_id=third_party_user_id,
        )

    def create_user_id(self) -> str:
        return self._repository.create_user_id()

    def bind_external_identity(self, user_id: str, im_type: str, third_party_user_id: str) -> str:
        return self._repository.bind_external_identity(
            user_id=user_id,
            im_type=im_type,
            third_party_user_id=third_party_user_id,
        )
