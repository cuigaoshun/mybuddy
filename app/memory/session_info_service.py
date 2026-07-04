from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.memory.models import ChatSessionInfo
from app.memory.repositories import ChatSessionInfoRepository

REPLY_LEASE_SECONDS = 30


class ChatSessionInfoService:
    """会话信息服务，负责维护会话详情与回复租约。"""

    def __init__(self, repository: ChatSessionInfoRepository) -> None:
        self._repository = repository

    def get_session_info(self, user_id: str, im_type: str, chat_id: str) -> ChatSessionInfo:
        return self._repository.get_session_info(user_id, im_type, chat_id)

    def acquire_reply_lease(self, user_id: str, im_type: str, chat_id: str) -> str | None:
        lease_owner = uuid4().hex
        lease_until = datetime.now(UTC) + timedelta(seconds=REPLY_LEASE_SECONDS)
        acquired = self._repository.try_acquire_reply_lease(
            user_id=user_id,
            im_type=im_type,
            chat_id=chat_id,
            lease_owner=lease_owner,
            lease_until=lease_until,
        )
        if not acquired:
            return None
        return lease_owner

    def update_session_info(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        first_reply_time: datetime | None = None,
        latest_reply_time: datetime | None = None,
        clear_lease_owner: str | None = None,
    ) -> None:
        self._repository.update_session_info(
            user_id=user_id,
            im_type=im_type,
            chat_id=chat_id,
            first_reply_time=first_reply_time,
            latest_reply_time=latest_reply_time,
            clear_lease_owner=clear_lease_owner,
        )
