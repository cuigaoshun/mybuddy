from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI
from loguru import logger

from app.core.config import AppRuntimeConfig
from app.gateway.dispatch.weixin import WeChatDispatcher
from app.storage.wechat_account_service import WeChatAccountService
from pkg.weixin.models import WeixinMessage
from pkg.weixin import WeixinApiClient, WeixinApiError


@dataclass(slots=True)
class WeChatPollingRunner:
    """统一管理微信账号长轮询任务。"""

    client: WeixinApiClient
    wechat_account_service: WeChatAccountService
    dispatcher: WeChatDispatcher
    runtime_config: AppRuntimeConfig
    tasks: list[asyncio.Task[None]] = field(default_factory=list)

    @asynccontextmanager
    async def start(self, app: FastAPI):
        # 把 runner 暴露到 app.state，便于扫码成功后追加拉起单账号任务。
        app.state.wechat_poller = self
        # 应用启动时扫描所有活跃账号，并为每个账号启动独立长轮询任务。
        for account in self.wechat_account_service.list_active_accounts():
            if not account.bot_account_id or not account.bot_token:
                continue
            self.start_account(account.bot_account_id)
        try:
            yield
        finally:
            await self.stop()

    def start_account(self, bot_account_id: str) -> None:
        # 同一个 bot 账号只保留一个活跃轮询任务，避免重复拉流。
        if any(getattr(task, "bot_account_id", None) == bot_account_id and not task.done() for task in self.tasks):
            return
        task = asyncio.create_task(self._poll_account(bot_account_id))
        setattr(task, "bot_account_id", bot_account_id)
        self.tasks.append(task)

    async def stop(self) -> None:
        for task in self.tasks:
            if not task.done():
                task.cancel()
        for task in self.tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _poll_account(self, bot_account_id: str) -> None:
        # 长轮询失败时使用简单指数退避，避免持续打满外部接口。
        retry_delay_seconds = 1.0
        while True:
            try:
                # 每轮都重新读取账号运行态，确保扫码重登或停用后能尽快退出。
                account = self.wechat_account_service.get_by_bot_account_id(bot_account_id)
                if account is None or not account.is_active or not account.bot_token:
                    return
                # 先拉取长轮询结果，成功后优先刷新账号级 cursor。
                updates = await asyncio.to_thread(
                    self.client.get_updates,
                    account.bot_token,
                    account.get_updates_buf or "",
                )
                if updates.get_updates_buf:
                    updated_account = self.wechat_account_service.update_runtime(
                        bot_account_id=bot_account_id,
                        third_party_user_id=None,
                        get_updates_buf=updates.get_updates_buf,
                        context_token=None,
                        source_message_id=None,
                    )
                    if updated_account is None:
                        # 如果账号状态没能更新成功，这一轮消息直接跳过，不继续分发到主链路。
                        logger.warning("微信账号运行态更新失败，跳过本轮分发，bot_account_id={bot_account_id}", bot_account_id=bot_account_id)
                        await asyncio.sleep(retry_delay_seconds)
                        retry_delay_seconds = min(retry_delay_seconds * 2, 10.0)
                        continue
                for message in updates.messages:
                    # 逐条消息刷新当前对端上下文，再交给 dispatcher 做统一归一化。
                    third_party_user_id = _resolve_third_party_user_id(message)
                    context_token = message.context_token
                    source_message_id = _resolve_message_id(message.message_id)
                    updated_account = self.wechat_account_service.update_runtime(
                        bot_account_id=bot_account_id,
                        third_party_user_id=third_party_user_id,
                        get_updates_buf=updates.get_updates_buf,
                        context_token=context_token,
                        source_message_id=source_message_id,
                    )
                    if updated_account is None:
                        # 单条消息级别的状态刷新失败时，只跳过当前消息，不结束整条长轮询。
                        logger.warning("微信账号运行态更新失败，跳过单条消息分发，bot_account_id={bot_account_id}", bot_account_id=bot_account_id)
                        continue
                    if self.runtime_config.is_development:
                        logger.info(
                            "收到微信消息，bot_account_id={bot_account_id} third_party_user_id={third_party_user_id} message_id={message_id}",
                            bot_account_id=bot_account_id,
                            third_party_user_id=third_party_user_id,
                            message_id=message.message_id,
                        )
                    else:
                        logger.info("收到微信消息，bot_account_id={bot_account_id}", bot_account_id=bot_account_id)
                    await self.dispatcher.dispatch_raw_message(message, bot_account_id)
                retry_delay_seconds = 1.0
            except asyncio.CancelledError:
                raise
            except WeixinApiError as exc:
                if exc.is_session_expired:
                    # 协议返回 -14 时，立即把当前账号标记成失效并停止该账号轮询。
                    logger.warning("微信账号 session 已过期，停止长轮询，bot_account_id={bot_account_id}", bot_account_id=bot_account_id)
                    self.wechat_account_service.mark_session_expired(bot_account_id)
                    return
                logger.exception("微信长轮询失败，bot_account_id={bot_account_id}", bot_account_id=bot_account_id)
            except Exception:
                logger.exception("微信长轮询异常，bot_account_id={bot_account_id}", bot_account_id=bot_account_id)
            await asyncio.sleep(retry_delay_seconds)
            retry_delay_seconds = min(retry_delay_seconds * 2, 10.0)


def _resolve_third_party_user_id(message: WeixinMessage) -> str | None:
    # 入站用户消息优先取发送方；必要时再退回接收方字段兜底。
    from_user_id = _resolve_optional_string(message.from_user_id)
    if from_user_id:
        return from_user_id
    return _resolve_optional_string(message.to_user_id)


def _resolve_optional_string(value: object) -> str | None:
    # 统一把空串折叠成 None，减少上层分支判断。
    return value if isinstance(value, str) and value != "" else None


def _resolve_message_id(value: object) -> str | None:
    # 平台 message_id 已在类模型层做过收口，这里只做空值兜底。
    if isinstance(value, str) and value != "":
        return value
    return None
