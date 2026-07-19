from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from loguru import logger
from pkg.weixin import WeixinApiError

router = APIRouter(prefix="/wechat", tags=["wechat"])


@router.get("/login")
async def start_wechat_login(request: Request, user_id: str | None = Query(default=None)) -> RedirectResponse:
    # 路由层只做参数接收和 service 编排，阻塞 I/O 下沉到线程池执行。
    container = request.app.state.container
    client = container.weixin_api_client()
    service = container.wechat_account_service()
    runtime_config = container.app_runtime_config()
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
    asyncio.create_task(_poll_wechat_login_until_terminal(request.app, qrcode_response.qrcode))
    # 当前接口改成直接跳转到二维码内容地址，扫码前的本地状态仍先落库。
    response = RedirectResponse(url=qrcode_response.qrcode_img_content, status_code=302)
    response.headers["X-WeChat-Qrcode"] = account.qrcode
    return response


@router.get("/login/status")
async def get_wechat_login_status(request: Request, user_id: str = Query(min_length=1)) -> dict[str, object]:
    # status 接口只查本地账号状态，当前改为按内部 user_id 查询。
    container = request.app.state.container
    service = container.wechat_account_service()
    account = await asyncio.to_thread(service.get_by_user_id, user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="未找到对应的微信账号记录")
    return {
        "status": account.qrcode_status,
        "user_id": account.user_id,
        "bot_account_id": account.bot_account_id,
    }


async def _poll_wechat_login_until_terminal(app, qrcode: str) -> None:
    container = app.state.container
    client = container.weixin_api_client()
    service = container.wechat_account_service()
    runtime_config = container.app_runtime_config()
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
            wechat_poller = getattr(app.state, "wechat_poller", None)
            if wechat_poller is not None and updated_account.bot_account_id:
                wechat_poller.start_account(updated_account.bot_account_id)
            return

        updated_account = await asyncio.to_thread(service.refresh_qrcode_status, qrcode, status.status)
        if updated_account is None:
            return
        if status.status == "expired":
            return
        with suppress(asyncio.CancelledError):
            await asyncio.sleep(2)
