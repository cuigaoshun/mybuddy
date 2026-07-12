from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.memory.models import ChatSessionInfo, PendingMemorySession
from app.memory.repositories import ChatSessionInfoRepository

# 单次回复租约的有效期，超过该时间后允许其他请求重新竞争租约。
REPLY_LEASE_SECONDS = 30
# 抢租约失败后的重试间隔秒数。
LEASE_RETRY_INTERVAL_SECONDS = 0.5
# 单条消息等待租约的最长时间，超时后放弃本次回复处理。
LEASE_ACQUIRE_TIMEOUT_SECONDS = 30


class ChatSessionInfoService:
    """会话信息服务，负责维护会话详情与回复租约。"""

    def __init__(self, repository: ChatSessionInfoRepository) -> None:
        self._repository = repository

    def get_session_info(self, user_id: str, im_type: str, chat_id: str) -> ChatSessionInfo:
        return self._repository.get_session_info(user_id, im_type, chat_id)

    def acquire_reply_lease(self, user_id: str, im_type: str, chat_id: str) -> str | None:
        deadline = datetime.now(UTC) + timedelta(seconds=LEASE_ACQUIRE_TIMEOUT_SECONDS)
        lease_owner = uuid4().hex

        while datetime.now(UTC) < deadline:
            lease_until = datetime.now(UTC) + timedelta(seconds=REPLY_LEASE_SECONDS)
            acquired = self._repository.try_acquire_reply_lease(
                user_id=user_id,
                im_type=im_type,
                chat_id=chat_id,
                lease_owner=lease_owner,
                lease_until=lease_until,
            )
            if acquired:
                return lease_owner
            time.sleep(LEASE_RETRY_INTERVAL_SECONDS)

        return None

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

    def list_sessions_pending_memory_processing(self, limit: int = 20) -> list[PendingMemorySession]:
        return self._repository.list_sessions_pending_memory_processing(limit=limit)
