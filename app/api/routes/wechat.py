from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from app.bootstrap.container import AppContainer
from loguru import logger
from app.core.config import AppRuntimeConfig
from app.storage.wechat_account_service import WeChatAccountService
from app.workers.wechat_poller import WeChatPollingRunner
from pkg.weixin import WeixinApiClient
from pkg.weixin import WeixinApiError

router = APIRouter(prefix="/wechat", tags=["wechat"])


@router.get("/login")
@inject
async def start_wechat_login(
    user_id: str | None = Query(default=None),
    client: WeixinApiClient = Depends(Provide[AppContainer.weixin_api_client]),
    service: WeChatAccountService = Depends(Provide[AppContainer.wechat_account_service]),
    runtime_config: AppRuntimeConfig = Depends(Provide[AppContainer.app_runtime_config]),
    wechat_poller: WeChatPollingRunner = Depends(Provide[AppContainer.wechat_poller_runner]),
) -> RedirectResponse:
    # 路由层只做参数接收和 service 编排，阻塞 I/O 下沉到线程池执行。
    qrcode_response = await asyncio.to_thread(client.get_bot_qrcode)
    # 扫码发起时先落待确认记录，必要时复用调用方传入的内部 user_id。
    account = await asyncio.to_thread(
        service.start_login,
        qrcode_response.qrcode,
        user_id,
    )
    if runtime_config.is_development:
        logger.info(
            "发起微信扫码登录，qrcode={qrcode} user_id={user_id}",
            qrcode=account.qrcode,
            user_id=account.user_id,
        )
    else:
        logger.info("发起微信扫码登录")
    # 登录入口负责启动后台轮询；后续 status 接口只读本地状态。
    asyncio.create_task(_poll_wechat_login_until_terminal(wechat_poller, client, service, runtime_config, qrcode_response.qrcode))
    # 当前接口改成直接跳转到二维码内容地址，扫码前的本地状态仍先落库。
    response = RedirectResponse(url=qrcode_response.qrcode_img_content, status_code=302)
    response.headers["X-WeChat-Qrcode"] = account.qrcode
    return response


@router.get("/login/status")
@inject
async def get_wechat_login_status(
    user_id: str = Query(min_length=1),
    service: WeChatAccountService = Depends(Provide[AppContainer.wechat_account_service]),
) -> dict[str, object]:
    # status 接口只查本地账号状态，当前改为按内部 user_id 查询。
    account = await asyncio.to_thread(service.get_by_user_id, user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="未找到对应的微信账号记录")
    return {
        "status": account.qrcode_status,
        "user_id": account.user_id,
        "bot_account_id": account.bot_account_id,
    }


async def _poll_wechat_login_until_terminal(
    wechat_poller: WeChatPollingRunner,
    client: WeixinApiClient,
    service: WeChatAccountService,
    runtime_config: AppRuntimeConfig,
    qrcode: str,
) -> None:
    deadline = datetime.now(UTC) + timedelta(minutes=1)

    while True:
        # 扫码后台轮询最长只保留一分钟，超时后停止本次登录流程跟进。
        if datetime.now(UTC) >= deadline:
            return
        account = await asyncio.to_thread(service.get_by_qrcode, qrcode)
        if account is None:
            return
        # 已经结束的扫码流程不再继续轮询外部状态。
        if account.qrcode_status in {"confirmed", "expired"}:
            return

        try:
            status = await asyncio.to_thread(client.get_qrcode_status, qrcode)
        except WeixinApiError:
            await asyncio.sleep(2)
            continue

        if status.status == "confirmed":
            if not status.bot_account_id or not status.bot_token:
                return
            updated_account = await asyncio.to_thread(
                service.complete_login,
                qrcode,
                status.bot_account_id,
                status.bot_token,
            )
            if updated_account is None:
                return
            if runtime_config.is_development:
                logger.info(
                    "微信扫码登录成功，qrcode={qrcode} user_id={user_id} bot_account_id={bot_account_id}",
                    qrcode=qrcode,
                    user_id=updated_account.user_id,
                    bot_account_id=updated_account.bot_account_id,
                )
            else:
                logger.info("微信扫码登录成功，bot_account_id={bot_account_id}", bot_account_id=updated_account.bot_account_id)
            if updated_account.bot_account_id:
                wechat_poller.start_account(updated_account.bot_account_id)
            return

        updated_account = await asyncio.to_thread(service.refresh_qrcode_status, qrcode, status.status)
        if updated_account is None:
            return
        if status.status == "expired":
            return
        with suppress(asyncio.CancelledError):
            await asyncio.sleep(2)
