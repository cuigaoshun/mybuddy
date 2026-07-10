from __future__ import annotations

from loguru import logger

from app.event.models import IncomingChatMessage
from app.memory.models import ASSISTANT_MESSAGE_TYPE, ChatSessionInfo, TEXT_CONTENT_TYPE, USER_MESSAGE_TYPE, MemoryRecord
from app.memory.service import ConversationMemoryService
from app.memory.session_info_service import ChatSessionInfoService
from .contracts import ChatAgent, MessageSender


class SessionManager:
    """会话编排入口，负责记忆写入、回复生成和消息发送。"""

    def __init__(
        self,
        message_sender: MessageSender,
        conversation_memory_service: ConversationMemoryService,
        chat_session_info_service: ChatSessionInfoService,
        chat_agent: ChatAgent,
    ) -> None:
        """注入消息发送器与对话记忆服务。"""
        self._message_sender = message_sender
        self._conversation_memory_service = conversation_memory_service
        self._chat_session_info_service = chat_session_info_service
        self._chat_agent = chat_agent

    def handle_message(self, message: IncomingChatMessage) -> None:
        """处理一条归一化后的消息，并落用户/助手两类记忆。"""
        is_first_user_message = self._conversation_memory_service.store(
            MemoryRecord(
                user_id=message.sender_id,
                chat_id=message.chat_id,
                message_id=message.message_id,
                message_type=USER_MESSAGE_TYPE,
                im_type=message.im_type,
                message_time=message.message_time,
                content_type=TEXT_CONTENT_TYPE,
                content={"text": message.text},
            ),
        )
        if not is_first_user_message:
            logger.info("消息已处理，跳过重复请求，message_id={message_id}", message_id=message.message_id)
            return

        lease_owner = self._chat_session_info_service.acquire_reply_lease(
            user_id=message.sender_id,
            im_type=message.im_type,
            chat_id=message.chat_id,
        )
        if lease_owner is None:
            logger.info(
                "等待回复租约超时，跳过本次回复，message_id={message_id}",
                message_id=message.message_id,
            )
            return

        session_info = self._chat_session_info_service.get_session_info(
            user_id=message.sender_id,
            im_type=message.im_type,
            chat_id=message.chat_id,
        )

        first_reply_time = None
        latest_reply_time = None
        try:
            if _is_reply_already_covered(session_info, message):
                logger.info(
                    "拿到租约后发现已有更新回复，跳过本次回复，message_id={message_id}",
                    message_id=message.message_id,
                )
                return

            reply_text = self._chat_agent.generate_reply(message, session_info)
            if reply_text is None:
                return

            # 只有发送成功后，才记录助手消息记忆。
            sent_message = self._message_sender.send_text(message.chat_id, reply_text)
            self._conversation_memory_service.store(
                MemoryRecord(
                    user_id=message.sender_id,
                    chat_id=sent_message.chat_id,
                    message_id=sent_message.message_id,
                    message_type=ASSISTANT_MESSAGE_TYPE,
                    im_type=sent_message.im_type,
                    message_time=sent_message.message_time,
                    content_type=TEXT_CONTENT_TYPE,
                    content={"text": sent_message.content},
                ),
            )
            first_reply_time = message.message_time
            latest_reply_time = message.message_time
        finally:
            self._chat_session_info_service.update_session_info(
                user_id=message.sender_id,
                im_type=message.im_type,
                chat_id=message.chat_id,
                first_reply_time=first_reply_time,
                latest_reply_time=latest_reply_time,
                clear_lease_owner=lease_owner,
            )


def _is_reply_already_covered(session_info: ChatSessionInfo, message: IncomingChatMessage) -> bool:
    if session_info.latest_reply_time is None:
        return False
    return session_info.latest_reply_time > message.message_time
