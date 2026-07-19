from __future__ import annotations

from loguru import logger

from app.event.models import IncomingChatMessage
from app.storage.models import ASSISTANT_MESSAGE_TYPE, ChatSessionInfo, TEXT_CONTENT_TYPE, USER_MESSAGE_TYPE, MemoryRecord
from app.storage.service import ConversationMemoryService
from app.storage.session_info_service import ChatSessionInfoService
from app.storage.user_identity_service import UserIdentityService
from app.services.im_sender.models import OutChatMessage, OutChatMessageExtra, WeixinOutChatExtra
from .contracts import ChatAgent, MessageSender


class SessionManager:
    """会话编排入口，负责记忆写入、回复生成和消息发送。"""

    def __init__(
        self,
        message_sender: MessageSender,
        conversation_memory_service: ConversationMemoryService,
        chat_session_info_service: ChatSessionInfoService,
        user_identity_service: UserIdentityService,
        chat_agent: ChatAgent,
    ) -> None:
        """注入消息发送器与对话记忆服务。"""
        self._message_sender = message_sender
        self._conversation_memory_service = conversation_memory_service
        self._chat_session_info_service = chat_session_info_service
        self._user_identity_service = user_identity_service
        self._chat_agent = chat_agent

    def handle_message(self, message: IncomingChatMessage) -> None:
        """处理一条归一化后的消息，并落用户/助手两类记忆。"""
        # 先把第三方身份收敛成系统内部 user_id，后续主链路只认内部用户。
        user_id = self._user_identity_service.get_or_create_user_id(
            im_type=message.im_type,
            third_party_user_id=message.third_party_user_id,
        )
        resolved_message = message.with_user_id(user_id)
        is_first_user_message = self._conversation_memory_service.store(
            MemoryRecord(
                user_id=user_id,
                chat_id=resolved_message.chat_id,
                message_id=resolved_message.message_id,
                message_type=USER_MESSAGE_TYPE,
                im_type=resolved_message.im_type,
                message_time=resolved_message.message_time,
                content_type=TEXT_CONTENT_TYPE,
                content={"text": resolved_message.text},
            ),
        )
        if not is_first_user_message:
            logger.info("消息已处理，跳过重复请求，message_id={message_id}", message_id=resolved_message.message_id)
            return

        lease_owner = self._chat_session_info_service.acquire_reply_lease(
            user_id=user_id,
            im_type=resolved_message.im_type,
            chat_id=resolved_message.chat_id,
        )
        if lease_owner is None:
            logger.info(
                "等待回复租约超时，跳过本次回复，message_id={message_id}",
                message_id=resolved_message.message_id,
            )
            return

        session_info = self._chat_session_info_service.get_session_info(
            user_id=user_id,
            im_type=resolved_message.im_type,
            chat_id=resolved_message.chat_id,
        )

        first_reply_time = None
        latest_reply_time = None
        typing_message = None
        typing_started = False
        try:
            if _is_reply_already_covered(session_info, resolved_message):
                logger.info(
                    "拿到租约后发现已有更新回复，跳过本次回复，message_id={message_id}",
                    message_id=resolved_message.message_id,
                )
                return

            # 收到微信消息后先通过统一 sender 接口把状态切到“输入中”。
            outgoing_extra = _build_outgoing_extra(resolved_message)
            typing_message = _build_outgoing_message(resolved_message, "", outgoing_extra)
            try:
                self._message_sender.set_typing_status(typing_message, True)
                typing_started = True
            except Exception:
                logger.exception("设置输入中状态失败，但继续生成回复，message_id={message_id}", message_id=resolved_message.message_id)
            reply_text = self._chat_agent.generate_reply(resolved_message, session_info)
            if reply_text is None:
                return

            # 先把当前回复封装成统一出站对象，再交给具体 sender 分平台处理。
            outgoing_message = _build_outgoing_message(resolved_message, reply_text, outgoing_extra)
            sent_message = self._message_sender.send_text(outgoing_message)
            # 只有发送成功后，才记录助手消息记忆。
            self._conversation_memory_service.store(
                MemoryRecord(
                    user_id=user_id,
                    chat_id=sent_message.chat_id,
                    message_id=sent_message.message_id,
                    message_type=ASSISTANT_MESSAGE_TYPE,
                    im_type=sent_message.im_type,
                    message_time=sent_message.message_time,
                    content_type=TEXT_CONTENT_TYPE,
                    content={"text": sent_message.content},
                ),
            )
            first_reply_time = resolved_message.message_time
            latest_reply_time = resolved_message.message_time
        finally:
            if typing_message is not None and typing_started:
                try:
                    self._message_sender.set_typing_status(typing_message, False)
                except Exception:
                    logger.exception("清理输入中状态失败，message_id={message_id}", message_id=resolved_message.message_id)
            self._chat_session_info_service.update_session_info(
                user_id=user_id,
                im_type=resolved_message.im_type,
                chat_id=resolved_message.chat_id,
                first_reply_time=first_reply_time,
                latest_reply_time=latest_reply_time,
                clear_lease_owner=lease_owner,
            )


def _is_reply_already_covered(session_info: ChatSessionInfo, message: IncomingChatMessage) -> bool:
    if session_info.latest_reply_time is None:
        return False
    return session_info.latest_reply_time > message.message_time


def _build_outgoing_extra(message: IncomingChatMessage) -> OutChatMessageExtra | None:
    # 微信即时回复场景优先把入站消息携带的上下文 token 透传给 sender。
    weixin_extra = None
    if message.extra is not None and message.extra.weixin is not None:
        weixin_extra = WeixinOutChatExtra(
            bot_account_id=message.extra.weixin.bot_account_id,
            context_token=message.extra.weixin.context_token,
        )
    return OutChatMessageExtra(weixin=weixin_extra) if weixin_extra is not None else None


def _build_outgoing_message(
    message: IncomingChatMessage,
    text: str,
    extra: OutChatMessageExtra | None,
) -> OutChatMessage:
    # 出站对象继续保留统一字段，平台附加信息放到 extra 里。
    return OutChatMessage(
        im_type=message.im_type,
        text=text,
        chat_id=message.chat_id,
        third_party_user_id=message.third_party_user_id,
        chat_type=message.chat_type,
        user_id=message.user_id,
        extra=extra,
    )
