from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger

from app.router.contracts import MessageSender
from app.services.im_sender.errors import SendMessageError
from app.services.im_sender.models import OutChatMessage
from app.storage.models import ASSISTANT_MESSAGE_TYPE, MemoryRecord, TEXT_CONTENT_TYPE
from app.storage.reminder_models import ReminderExecutionBundle
from app.storage.reminder_repository import ReminderRepository
from app.storage.reminder_service import ReminderService
from app.storage.service import ConversationMemoryService
from app.storage.wechat_account_service import WeChatAccountService


class ReminderExecutionService:
    """提醒执行服务，负责组装文案、发送并回写结果。"""

    def __init__(
        self,
        repository: ReminderRepository,
        reminder_service: ReminderService,
        reminder_graph,
        message_sender: MessageSender,
        conversation_memory_service: ConversationMemoryService,
        wechat_account_service: WeChatAccountService,
    ) -> None:
        self._repository = repository
        self._reminder_service = reminder_service
        self._reminder_graph = reminder_graph
        self._message_sender = message_sender
        self._conversation_memory_service = conversation_memory_service
        self._wechat_account_service = wechat_account_service

    def execute_job(self, job_id: int) -> None:
        """执行一条已认领的提醒任务。"""

        bundle = self._repository.get_execution_bundle(job_id)
        if bundle is None:
            return
        final_text = self._build_final_text(bundle)
        outgoing_message = self._build_outgoing_message(bundle=bundle, text=final_text)
        if outgoing_message is None:
            self._reminder_service.mark_job_blocked_user_route(
                job_id=job_id,
                attempt_count=bundle.job.attempt_count,
                error_message="当前无法根据 user_id 解析可用发送路由",
            )
            return
        try:
            sent_message = self._message_sender.send_text(outgoing_message)
        except SendMessageError as exc:
            if self._is_blocked_user_route_error(bundle=bundle, error=exc):
                self._reminder_service.mark_job_blocked_user_route(
                    job_id=job_id,
                    attempt_count=bundle.job.attempt_count,
                    error_message=str(exc),
                )
            else:
                self._reminder_service.mark_job_retryable(
                    job_id=job_id,
                    attempt_count=bundle.job.attempt_count,
                    error_message=str(exc),
                )
            return
        self._repository.mark_job_sent(
            job_id=job_id,
            sent_message_id=sent_message.message_id,
            sent_at=sent_message.message_time,
        )
        self._store_sent_memory(bundle=bundle, sent_message=sent_message)

    def _store_sent_memory(self, bundle: ReminderExecutionBundle, sent_message) -> None:  # noqa: ANN001
        try:  # noqa: BROAD_EXCEPT_OK
            self._conversation_memory_service.store(
                MemoryRecord(
                    user_id=bundle.schedule.user_id,
                    chat_id=sent_message.chat_id,
                    message_id=sent_message.message_id,
                    message_type=ASSISTANT_MESSAGE_TYPE,
                    im_type=sent_message.im_type,
                    message_time=sent_message.message_time,
                    content_type=TEXT_CONTENT_TYPE,
                    content={"text": sent_message.content},
                )
            )
        except Exception:  # noqa: BROAD_EXCEPT_OK
            logger.exception(
                "提醒发送成功，但写入 assistant memory 失败，schedule_id={schedule_id} job_id={job_id}",
                schedule_id=bundle.schedule.id,
                job_id=bundle.job.id,
            )

    def _is_blocked_user_route_error(self, bundle: ReminderExecutionBundle, error: SendMessageError) -> bool:
        schedule = bundle.schedule
        if schedule.im_type != "wechat":
            return False
        blocked_fragments = (
            "context_token",
            "微信账号未登录或不存在",
            "缺少微信聊天对端 ID",
        )
        return any(fragment in str(error) for fragment in blocked_fragments)

    def _build_final_text(self, bundle: ReminderExecutionBundle) -> str:
        conversation_context = self._conversation_memory_service.build_reminder_context(
            user_id=bundle.schedule.user_id,
            im_type=bundle.schedule.im_type,
            chat_id=bundle.schedule.chat_id,
            source_message_id=bundle.schedule.source_message_id,
        )
        result = self._reminder_graph.invoke(
            {
                "schedule": bundle.schedule,
                "job": bundle.job,
                "conversation_context": conversation_context,
            }
        )
        final_text = result.get("final_text")
        if isinstance(final_text, str) and final_text.strip() != "":
            return final_text.strip()
        return f"提醒你：{bundle.schedule.reminder_text}"

    def _build_outgoing_message(self, bundle: ReminderExecutionBundle, text: str) -> OutChatMessage | None:
        schedule = bundle.schedule
        match schedule.im_type:
            case "feishu":
                return OutChatMessage(
                    im_type=schedule.im_type,
                    text=text,
                    chat_id=schedule.chat_id,
                    third_party_user_id=schedule.third_party_user_id,
                    chat_type=schedule.chat_type,
                    user_id=schedule.user_id,
                    extra=None,
                )
            case "wechat":
                account = self._wechat_account_service.get_by_user_id(schedule.user_id)
                if account is None or account.third_party_user_id is None:
                    return None
                return OutChatMessage(
                    im_type=schedule.im_type,
                    text=text,
                    chat_id=account.third_party_user_id,
                    third_party_user_id=account.third_party_user_id,
                    chat_type=schedule.chat_type,
                    user_id=schedule.user_id,
                    extra=None,
                )
            case _:
                return None
