from __future__ import annotations

from app.storage.models import WeChatAccount
from app.storage.repositories import WeChatAccountRepository
from app.storage.user_identity_service import UserIdentityService

WECHAT_IDENTITY_TYPE = "wechat"
QRCODE_STATUS_WAIT = "wait"
QRCODE_STATUS_SCANED = "scaned"
QRCODE_STATUS_CONFIRMED = "confirmed"
QRCODE_STATUS_EXPIRED = "expired"


class WeChatAccountService:
    """微信账号运行态服务。"""

    def __init__(self, repository: WeChatAccountRepository, user_identity_service: UserIdentityService) -> None:
        # 账号运行态的读写统一走仓储。
        self._repository = repository
        # 用户身份绑定与自动建用户继续复用现有身份服务。
        self._user_identity_service = user_identity_service

    def start_login(self, qrcode: str, user_id: str | None) -> WeChatAccount:
        # 如果调用方已经指定内部 user_id，优先复用该用户的旧账号记录并刷新二维码。
        if user_id:
            existing = self._repository.get_by_user_id(user_id)
            if existing is not None:
                return self._repository.refresh_pending_login(
                    user_id=user_id,
                    qrcode=qrcode,
                    qrcode_status=QRCODE_STATUS_WAIT,
                )
        # 没有指定内部用户时，先写一条待确认登录记录，后续扫码成功后再补 user_id。
        return self._repository.create_pending_login(
            qrcode=qrcode,
            qrcode_status=QRCODE_STATUS_WAIT,
            user_id=user_id,
        )

    def refresh_qrcode_status(self, qrcode: str, qrcode_status: str) -> WeChatAccount | None:
        # 二维码轮询阶段只刷新状态，不提前写入账号正式凭证。
        return self._repository.update_qrcode_status(qrcode=qrcode, qrcode_status=qrcode_status)

    def get_by_qrcode(self, qrcode: str) -> WeChatAccount | None:
        return self._repository.get_by_qrcode(qrcode)

    def complete_login(self, qrcode: str, bot_account_id: str, bot_token: str) -> WeChatAccount | None:
        # 先用二维码反查这次登录流程对应的账号记录。
        account = self._repository.get_by_qrcode(qrcode)
        if account is None:
            return None

        # 如果扫码前没有指定内部 user_id，这里补建一个系统内部用户。
        user_id = account.user_id or self._user_identity_service.create_user_id()
        return self._repository.complete_login(
            qrcode=qrcode,
            user_id=user_id,
            bot_account_id=bot_account_id,
            bot_token=bot_token,
            qrcode_status=QRCODE_STATUS_CONFIRMED,
        )

    def list_active_accounts(self) -> list[WeChatAccount]:
        return self._repository.list_active_accounts()

    def get_by_user_id(self, user_id: str) -> WeChatAccount | None:
        return self._repository.get_by_user_id(user_id)

    def get_by_bot_account_id(self, bot_account_id: str) -> WeChatAccount | None:
        return self._repository.get_by_bot_account_id(bot_account_id)

    def mark_session_expired(self, bot_account_id: str) -> WeChatAccount | None:
        # 收到 -14 后把当前账号的可用运行态整体作废。
        return self._repository.mark_session_expired(bot_account_id)

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
        # 运行态更新统一下沉到仓储，避免 runner 或 sender 直接拼 SQL。
        account = self._repository.update_runtime(
            bot_account_id=bot_account_id,
            third_party_user_id=third_party_user_id,
            get_updates_buf=get_updates_buf,
            context_token=context_token,
            source_message_id=source_message_id,
            typing_ticket=typing_ticket,
        )
        if account is None:
            return None
        # 当收到新的微信对端 ID 时，同步把它绑定进现有第三方身份映射表。
        if account.user_id and third_party_user_id:
            self._user_identity_service.bind_external_identity(
                user_id=account.user_id,
                im_type=WECHAT_IDENTITY_TYPE,
                third_party_user_id=third_party_user_id,
            )
        return account
