from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WeixinQrCode:
    qrcode: str
    qrcode_img_content: str


@dataclass(frozen=True, slots=True)
class WeixinQrStatus:
    status: str
    bot_token: str | None = None
    bot_account_id: str | None = None
    authorized_user_id: str | None = None


@dataclass(frozen=True, slots=True)
class WeixinTextItem:
    text: str | None = None


@dataclass(frozen=True, slots=True)
class WeixinImageItem:
    url: str | None = None


@dataclass(frozen=True, slots=True)
class WeixinVoiceItem:
    text: str | None = None


@dataclass(frozen=True, slots=True)
class WeixinFileItem:
    file_name: str | None = None


@dataclass(frozen=True, slots=True)
class WeixinMessageItem:
    # 平台原始 item 类型，当前常见值为 1~5。
    item_type: int | None
    text_item: WeixinTextItem | None = None
    image_item: WeixinImageItem | None = None
    voice_item: WeixinVoiceItem | None = None
    file_item: WeixinFileItem | None = None


@dataclass(frozen=True, slots=True)
class WeixinMessage:
    # 平台消息 ID，统一收口成字符串。
    message_id: str
    # 微信发送方 ID，例如 ...@im.wechat。
    from_user_id: str | None
    # 微信接收方 ID，例如 ...@im.bot。
    to_user_id: str | None
    # 平台原始消息类型，当前只处理 1=USER。
    message_type: int | None
    # 回复当前会话必须带回的上下文 token。
    context_token: str | None
    # 毫秒时间戳。
    create_time_ms: int | None
    # 平台 item 列表已收口成明确类模型，后续链路不再直接依赖裸 dict。
    item_list: tuple[WeixinMessageItem, ...]


@dataclass(frozen=True, slots=True)
class WeixinUpdatesResponse:
    messages: tuple[WeixinMessage, ...]
    get_updates_buf: str
    longpolling_timeout_ms: int | None = None
