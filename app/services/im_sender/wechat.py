from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import AppRuntimeConfig
from app.event.models import IM_TYPE_WECHAT
from app.services.im_sender.errors import SendMessageError
from app.services.im_sender.models import OutChatMessage, SentMessageResult
from app.storage.wechat_account_service import WeChatAccountService
from pkg.weixin import WeixinApiClient, WeixinApiError
from loguru import logger


class WeChatMessageSender:
    """微信消息发送实现。"""

    def __init__(self, client: WeixinApiClient, wechat_account_service: WeChatAccountService, runtime_config: AppRuntimeConfig) -> None:
        # 微信 HTTP 能力由 pkg/weixin 统一封装。
        self._client = client
        # 账号运行态和上下文缓存统一通过 service 读取和刷新。
        self._wechat_account_service = wechat_account_service
        # dev/prod 下日志详细程度不同，发送器直接复用运行时配置判断。
        self._runtime_config = runtime_config

    def send_text(self, message: OutChatMessage) -> SentMessageResult:
        # 先按 bot_account_id，回退到 user_id 查当前账号，避免 sender 自己拼查询逻辑。
        account = _resolve_account(self._wechat_account_service, message)
        if account is None or account.bot_account_id is None or account.bot_token is None:
            raise SendMessageError(message.chat_id, 400, "微信账号未登录或不存在", im_type=IM_TYPE_WECHAT)

        # 目标对端优先用统一出站对象携带的用户 ID，缺失时再回退到账号缓存。
        target_user_id = message.third_party_user_id or account.third_party_user_id
        if not target_user_id:
            raise SendMessageError(message.chat_id, 400, "缺少微信聊天对端 ID", im_type=IM_TYPE_WECHAT)

        # 当前消息即时回复时优先使用 extra 里的 token，缺失时再回退到账号缓存值。
        context_token = _resolve_context_token(message, account.context_token)
        if not context_token:
            raise SendMessageError(message.chat_id, 400, "缺少可用的 context_token", im_type=IM_TYPE_WECHAT)

        try:
            if self._runtime_config.is_development:
                logger.info(
                    "发送微信消息，bot_account_id={bot_account_id} third_party_user_id={third_party_user_id} chat_id={chat_id} text={text}",
                    bot_account_id=account.bot_account_id,
                    third_party_user_id=target_user_id,
                    chat_id=message.chat_id,
                    text=message.text,
                )
            else:
                logger.info(
                    "发送微信消息，bot_account_id={bot_account_id} chat_id={chat_id}",
                    bot_account_id=account.bot_account_id,
                    chat_id=message.chat_id,
                )
            self._client.send_text(account.bot_token, target_user_id, context_token, message.text)
        except WeixinApiError as exc:
            if exc.is_session_expired:
                # 协议返回 -14 时，主动把账号运行态置为失效，等待重新扫码登录。
                self._wechat_account_service.mark_session_expired(account.bot_account_id)
            raise SendMessageError(message.chat_id, exc.code or exc.status, str(exc), im_type=IM_TYPE_WECHAT) from exc
        # 微信当前发送接口不回真正的 message_id，这里生成本地唯一出站 ID，避免记忆回写时被空 ID 去重吞掉。
        return SentMessageResult(
            im_type=IM_TYPE_WECHAT,
            chat_id=message.chat_id,
            message_id=f"wechat-out-{uuid4().hex}",
            content=message.text,
            message_time=datetime.now(timezone.utc),
        )

    def set_typing_status(self, message: OutChatMessage, is_typing: bool) -> None:
        account = _resolve_account(self._wechat_account_service, message)
        if account is None or account.bot_account_id is None or account.bot_token is None:
            return

        target_user_id = message.third_party_user_id or account.third_party_user_id
        if not target_user_id:
            return

        context_token = _resolve_context_token(message, account.context_token)
        if not context_token:
            return

        status = 1 if is_typing else 2
        try:
            typing_ticket = account.typing_ticket
            if not typing_ticket:
                typing_ticket = _refresh_typing_ticket(
                    self._client,
                    self._wechat_account_service,
                    account.bot_account_id,
                    account.bot_token,
                    target_user_id,
                    context_token,
                )
            if not typing_ticket:
                return
            try:
                self._client.send_typing(account.bot_token, target_user_id, typing_ticket, status)
            except WeixinApiError as exc:
                if exc.is_session_expired:
                    self._wechat_account_service.mark_session_expired(account.bot_account_id)
                    return
                # 如果旧 ticket 已失效，这里刷新一次新 ticket，写回库后再重试一次。
                typing_ticket = _refresh_typing_ticket(
                    self._client,
                    self._wechat_account_service,
                    account.bot_account_id,
                    account.bot_token,
                    target_user_id,
                    context_token,
                )
                if not typing_ticket:
                    return
                self._client.send_typing(account.bot_token, target_user_id, typing_ticket, status)
        except WeixinApiError as exc:
            if exc.is_session_expired:
                self._wechat_account_service.mark_session_expired(account.bot_account_id)
                return
            raise SendMessageError(message.chat_id, exc.code or exc.status, str(exc), im_type=IM_TYPE_WECHAT) from exc


def _resolve_account(wechat_account_service: WeChatAccountService, message: OutChatMessage):
    # 先按 bot 账号查，避免一个内部用户将来挂多个账号时误取错记录。
    if message.extra and message.extra.weixin and message.extra.weixin.bot_account_id:
        account = wechat_account_service.get_by_bot_account_id(message.extra.weixin.bot_account_id)
        if account is not None:
            return account
    return wechat_account_service.get_by_user_id(message.user_id)


def _resolve_context_token(message: OutChatMessage, fallback_context_token: str | None) -> str | None:
    # extra 里的 token 代表“当前入站消息即时可用”的回复上下文，优先级高于缓存值。
    if message.extra and message.extra.weixin and message.extra.weixin.context_token:
        return message.extra.weixin.context_token
    return fallback_context_token


def _refresh_typing_ticket(
    client: WeixinApiClient,
    wechat_account_service: WeChatAccountService,
    bot_account_id: str,
    bot_token: str,
    third_party_user_id: str,
    context_token: str,
) -> str | None:
    # 统一收口 ticket 刷新和写回库逻辑，避免在多处分支里重复拼一遍。
    typing_ticket = client.get_typing_ticket(bot_token, third_party_user_id, context_token)
    if not typing_ticket:
        return None
    wechat_account_service.update_runtime(
        bot_account_id=bot_account_id,
        third_party_user_id=None,
        get_updates_buf=None,
        context_token=None,
        source_message_id=None,
        typing_ticket=typing_ticket,
    )
    return typing_ticket
