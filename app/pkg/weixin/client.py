from __future__ import annotations

import base64
import json
import os
from urllib.parse import quote, urljoin

import httpx
from .errors import WeixinApiError
from .models import (
    WeixinFileItem,
    WeixinImageItem,
    WeixinMessage,
    WeixinMessageItem,
    WeixinQrCode,
    WeixinQrStatus,
    WeixinTextItem,
    WeixinUpdatesResponse,
    WeixinVoiceItem,
)

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CHANNEL_VERSION = "1.0.0"


class WeixinApiClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        # 一期默认打固定官方基座地址，去掉末尾斜杠以便统一拼 URL。
        self._base_url = base_url.rstrip("/")

    def get_bot_qrcode(self) -> WeixinQrCode:
        # 扫码发起阶段需要二维码 token 和二维码内容两项数据。
        payload = self._api_get("/ilink/bot/get_bot_qrcode?bot_type=3")
        qrcode = payload.get("qrcode")
        qrcode_img_content = payload.get("qrcode_img_content")
        if not isinstance(qrcode, str) or not isinstance(qrcode_img_content, str):
            raise WeixinApiError("二维码响应缺少必要字段", status=200, payload=payload)
        return WeixinQrCode(qrcode=qrcode, qrcode_img_content=qrcode_img_content)

    def get_qrcode_status(self, qrcode: str) -> WeixinQrStatus:
        # 二维码状态轮询只依赖 qrcode token，不需要提前持有 bot_token。
        payload = self._api_get(
            f"/ilink/bot/get_qrcode_status?qrcode={quote(qrcode, safe='')}",
            headers={"iLink-App-ClientVersion": "1"},
        )
        status = payload.get("status")
        if not isinstance(status, str):
            raise WeixinApiError("二维码状态响应缺少 status", status=200, payload=payload)
        bot_token = payload.get("bot_token")
        bot_account_id = payload.get("ilink_bot_id")
        authorized_user_id = payload.get("ilink_user_id")
        return WeixinQrStatus(
            status=status,
            bot_token=bot_token if isinstance(bot_token, str) else None,
            bot_account_id=bot_account_id if isinstance(bot_account_id, str) else None,
            authorized_user_id=authorized_user_id if isinstance(authorized_user_id, str) else None,
        )

    def get_updates(self, bot_token: str, get_updates_buf: str) -> WeixinUpdatesResponse:
        # 长轮询是账号级能力，因此只接受 bot_token 和账号级 cursor。
        payload = self._api_post(
            "/ilink/bot/getupdates",
            {
                "get_updates_buf": get_updates_buf,
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
            bot_token=bot_token,
            timeout_seconds=40,
        )
        raw_messages = payload.get("msgs")
        next_buf = payload.get("get_updates_buf")
        if not isinstance(raw_messages, list) or not isinstance(next_buf, str):
            raise WeixinApiError("长轮询响应缺少必要字段", status=200, payload=payload)
        timeout_value = payload.get("longpolling_timeout_ms")
        timeout_ms = timeout_value if isinstance(timeout_value, int) else None
        normalized_messages = tuple(_to_weixin_message(message) for message in raw_messages if isinstance(message, dict))
        return WeixinUpdatesResponse(
            messages=normalized_messages,
            get_updates_buf=next_buf,
            longpolling_timeout_ms=timeout_ms,
        )

    def send_text(self, bot_token: str, third_party_user_id: str, context_token: str, text: str) -> None:
        # 发送文本时同时要带对端 ID 和当前上下文 token，这两者缺一不可。
        self._api_post(
            "/ilink/bot/sendmessage",
            {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": third_party_user_id,
                    "client_id": _generate_client_id(),
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": context_token,
                    "item_list": [
                        {
                            "type": 1,
                            "text_item": {"text": text},
                        }
                    ],
                },
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
            bot_token=bot_token,
            timeout_seconds=15,
        )

    def get_typing_ticket(self, bot_token: str, third_party_user_id: str, context_token: str) -> str | None:
        # typing ticket 通过 getconfig 按当前对端与上下文获取。
        payload = self._api_post(
            "/ilink/bot/getconfig",
            {
                "ilink_user_id": third_party_user_id,
                "context_token": context_token,
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
            bot_token=bot_token,
            timeout_seconds=15,
        )
        ticket = payload.get("typing_ticket")
        return ticket if isinstance(ticket, str) else None

    def send_typing(self, bot_token: str, third_party_user_id: str, typing_ticket: str, status: int) -> None:
        # status=1 表示开始输入，status=2 表示取消输入状态。
        self._api_post(
            "/ilink/bot/sendtyping",
            {
                "ilink_user_id": third_party_user_id,
                "typing_ticket": typing_ticket,
                "status": status,
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
            bot_token=bot_token,
            timeout_seconds=15,
        )

    def _api_get(self, path: str, headers: dict[str, str] | None = None) -> dict[str, object]:
        # GET 接口主要用于扫码登录阶段，不走 bot_token 鉴权。
        request = httpx.Request(
            method="GET",
            url=urljoin(f"{self._base_url}/", path.lstrip("/")),
            headers=headers or {},
        )
        return _execute_request(request, timeout_seconds=30)

    def _api_post(
        self,
        path: str,
        payload: dict[str, object],
        *,
        bot_token: str,
        timeout_seconds: int,
    ) -> dict[str, object]:
        # 所有业务 POST 都统一补上协议要求的鉴权头和 X-WECHAT-UIN。
        request = httpx.Request(
            method="POST",
            url=urljoin(f"{self._base_url}/", path.lstrip("/")),
            headers={
                "Content-Type": "application/json",
                "AuthorizationType": "ilink_bot_token",
                "Authorization": f"Bearer {bot_token}",
                "X-WECHAT-UIN": _random_wechat_uin(),
            },
            content=json.dumps(payload).encode("utf-8"),
        )
        return _execute_request(request, timeout_seconds=timeout_seconds)


def _execute_request(request: httpx.Request, timeout_seconds: int) -> dict[str, object]:
    # 统一收口 HTTP 层和业务 ret/errcode 错误，外层只处理 WeixinApiError。
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.send(request)
            status = response.status_code
            payload = _read_json_payload(response.content)
    except WeixinApiError:
        raise
    except httpx.HTTPError as exc:
        raise WeixinApiError(str(exc), status=500) from exc
    except Exception as exc:
        raise WeixinApiError(str(exc), status=500) from exc

    if not isinstance(payload, dict):
        raise WeixinApiError("微信接口响应不是合法 JSON 对象", status=status, payload=payload)
    ret_value = payload.get("ret")
    errcode_value = payload.get("errcode")
    error_code = errcode_value if isinstance(errcode_value, int) else ret_value if isinstance(ret_value, int) and ret_value != 0 else None
    if status < 200 or status >= 300:
        raise WeixinApiError(str(payload.get("errmsg") or f"HTTP {status}"), status=status, code=error_code, payload=payload)
    if isinstance(ret_value, int) and ret_value != 0:
        raise WeixinApiError(str(payload.get("errmsg") or "微信接口业务失败"), status=status, code=error_code, payload=payload)
    if isinstance(errcode_value, int) and errcode_value != 0:
        raise WeixinApiError(str(payload.get("errmsg") or "微信接口业务失败"), status=status, code=error_code, payload=payload)
    return payload


def _read_json_payload(raw_bytes: bytes) -> object:
    # 空响应体按空对象处理，避免每个调用点重复做空值分支。
    text = raw_bytes.decode("utf-8") if raw_bytes else ""
    return json.loads(text) if text else {}


def _random_wechat_uin() -> str:
    # 协议要求每次业务请求都带一个随机 X-WECHAT-UIN。
    value = int.from_bytes(os.urandom(4), "big")
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _generate_client_id() -> str:
    # 出站 client_id 由系统侧生成，保证同一进程内尽量唯一。
    random_suffix = base64.b16encode(os.urandom(6)).decode("ascii").lower()
    timestamp = str(int.from_bytes(os.urandom(4), "big"))
    return f"mybuddy-wechat:{timestamp}-{random_suffix}"


def _to_weixin_message(payload: dict[str, object]) -> WeixinMessage:
    # 把平台原始响应收口成明确类模型，后续链路不再直接依赖裸 dict。
    raw_message_id = payload.get("message_id")
    message_id = str(raw_message_id) if isinstance(raw_message_id, int | str) else ""
    raw_items = payload.get("item_list")
    item_list = tuple(_to_weixin_message_item(item) for item in raw_items if isinstance(item, dict)) if isinstance(raw_items, list) else ()
    create_time_ms = payload.get("create_time_ms")
    raw_message_type = payload.get("message_type")
    return WeixinMessage(
        message_id=message_id,
        from_user_id=payload.get("from_user_id") if isinstance(payload.get("from_user_id"), str) else None,
        to_user_id=payload.get("to_user_id") if isinstance(payload.get("to_user_id"), str) else None,
        message_type=raw_message_type if isinstance(raw_message_type, int) else None,
        context_token=payload.get("context_token") if isinstance(payload.get("context_token"), str) else None,
        create_time_ms=create_time_ms if isinstance(create_time_ms, int) else int(create_time_ms) if isinstance(create_time_ms, str) and create_time_ms.strip().isdigit() else None,
        item_list=item_list,
    )


def _to_weixin_message_item(payload: dict[str, object]) -> WeixinMessageItem:
    # item 子结构按常见类型做最小收口，不在 client 层承担复杂业务判断。
    raw_item_type = payload.get("type")
    text_payload = payload.get("text_item")
    image_payload = payload.get("image_item")
    voice_payload = payload.get("voice_item")
    file_payload = payload.get("file_item")
    return WeixinMessageItem(
        item_type=raw_item_type if isinstance(raw_item_type, int) else None,
        text_item=WeixinTextItem(text=text_payload.get("text") if isinstance(text_payload, dict) and isinstance(text_payload.get("text"), str) else None),
        image_item=WeixinImageItem(url=image_payload.get("url") if isinstance(image_payload, dict) and isinstance(image_payload.get("url"), str) else None),
        voice_item=WeixinVoiceItem(text=voice_payload.get("text") if isinstance(voice_payload, dict) and isinstance(voice_payload.get("text"), str) else None),
        file_item=WeixinFileItem(file_name=file_payload.get("file_name") if isinstance(file_payload, dict) and isinstance(file_payload.get("file_name"), str) else None),
    )
