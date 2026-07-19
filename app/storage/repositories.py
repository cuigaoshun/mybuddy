from __future__ import annotations

from datetime import datetime
from typing import Collection, Protocol

from app.storage.models import ChatSessionInfo, ExternalUserIdentity, MemoryRecord, PendingMemorySession, RetrievedMemoryHit, UserMemory, WeChatAccount


class ConversationMemoryRepository(Protocol):
    def save(self, record: MemoryRecord, vector: list[float]) -> bool:
        ...

    def list_recent_by_user(
        self,
        user_id: str,
        exclude_message_id: str | None = None,
    ) -> list[MemoryRecord]:
        ...

    def search_similar_by_user(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        query_vector: list[float],
        limit: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        ...

    def search_similar_hits_by_user(
        self,
        user_id: str,
        query_vector: list[float],
        limit: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[RetrievedMemoryHit]:
        ...

    def search_text_by_user(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        query_text: str,
        limit: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        ...

    def list_by_time_range(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        ...

    def list_message_windows_by_message_ids(
        self,
        user_id: str,
        message_ids: Collection[str],
        exclude_message_ids: Collection[str] | None = None,
    ) -> list[MemoryRecord]:
        ...

    def list_after_message_id(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        after_message_id: str | None,
        limit: int,
    ) -> list[MemoryRecord]:
        ...


class ChatSessionInfoRepository(Protocol):
    def get_session_info(self, user_id: str, im_type: str, chat_id: str) -> ChatSessionInfo:
        ...

    def try_acquire_reply_lease(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        lease_owner: str,
        lease_until: datetime,
    ) -> bool:
        ...

    def update_session_info(
        self,
        user_id: str,
        im_type: str,
        chat_id: str,
        first_reply_time: datetime | None = None,
        latest_reply_time: datetime | None = None,
        clear_lease_owner: str | None = None,
    ) -> None:
        ...

    def list_sessions_pending_memory_processing(self, limit: int) -> list[PendingMemorySession]:
        ...


class UserMemoryRepository(Protocol):
    def get_by_user(self, user_id: str) -> UserMemory | None:
        ...

    def save(self, user_memory: UserMemory) -> None:
        ...


class UserIdentityRepository(Protocol):
    def get_by_external_identity(self, im_type: str, third_party_user_id: str) -> ExternalUserIdentity | None:
        ...

    def get_or_create_user_id(self, im_type: str, third_party_user_id: str) -> str:
        ...

    def create_user_id(self) -> str:
        ...

    def bind_external_identity(self, user_id: str, im_type: str, third_party_user_id: str) -> str:
        ...


class WeChatAccountRepository(Protocol):
    def get_by_qrcode(self, qrcode: str) -> WeChatAccount | None:
        ...

    def get_by_user_id(self, user_id: str) -> WeChatAccount | None:
        ...

    def get_by_bot_account_id(self, bot_account_id: str) -> WeChatAccount | None:
        ...

    def mark_session_expired(self, bot_account_id: str) -> WeChatAccount | None:
        ...

    def create_pending_login(self, qrcode: str, qrcode_status: str, user_id: str | None) -> WeChatAccount:
        ...

    def refresh_pending_login(self, user_id: str, qrcode: str, qrcode_status: str) -> WeChatAccount:
        ...

    def complete_login(
        self,
        qrcode: str,
        user_id: str,
        bot_account_id: str,
        bot_token: str,
        qrcode_status: str,
    ) -> WeChatAccount | None:
        ...

    def update_qrcode_status(self, qrcode: str, qrcode_status: str) -> WeChatAccount | None:
        ...

    def update_runtime(
        self,
        bot_account_id: str,
        *,
        third_party_user_id: str | None,
        get_updates_buf: str | None,
        context_token: str | None,
        source_message_id: str | None,
        typing_ticket: str | None = None,
    ) -> WeChatAccount | None:
        ...

    def list_active_accounts(self) -> list[WeChatAccount]:
        ...
