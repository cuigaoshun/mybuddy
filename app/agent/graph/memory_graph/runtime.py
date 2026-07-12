from __future__ import annotations

from dataclasses import dataclass

from app.memory.service import ConversationMemoryService
from app.memory.session_info_service import ChatSessionInfoService
from app.memory.user_memory_service import UserMemoryService


@dataclass(frozen=True)
class MemoryGraphServices:
    """长期记忆处理图共享服务。"""

    conversation_memory_service: ConversationMemoryService
    chat_session_info_service: ChatSessionInfoService
    user_memory_service: UserMemoryService
