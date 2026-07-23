from datetime import datetime

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from app.agent.context.tools.models import RegisteredTool, ToolDefinition
from app.agent.context.tools.tool_runtime import get_reply_state
from app.storage.reminder_models import CreatedReminder, ReminderCreateCommand
from app.storage.reminder_service import ReminderService, ReminderValidationError

from .models import CreateReminderToolInput, WRITE_TOOLS_CATEGORY


class ReminderToolDefinition(ToolDefinition):
    """统一封装提醒创建工具。"""

    @classmethod
    def build(cls, reminder_service: ReminderService) -> RegisteredTool:
        """基于 reminder service 构建提醒创建工具。"""

        @tool("create_reminder", args_schema=CreateReminderToolInput)
        def create_reminder_tool(
            runtime: ToolRuntime,
            reminder_text: str,
            run_at: str | None = None,
            cron_expr: str | None = None,
        ) -> str:
            """创建一次性或重复提醒；重复提醒频率不能高于每 8 小时一次。"""

            state = get_reply_state(runtime)
            if state is None:
                return "当前缺少会话状态，无法创建提醒。"
            try:
                created = reminder_service.create_reminder(
                    ReminderCreateCommand(
                        user_id=state.message.user_id,
                        im_type=state.message.im_type,
                        chat_id=state.message.chat_id,
                        third_party_user_id=state.message.third_party_user_id,
                        chat_type=state.message.chat_type,
                        reminder_text=reminder_text,
                        source_message_id=state.message.message_id,
                        source_message_time=state.message.message_time,
                        source_text=state.message.text,
                        run_at=_parse_optional_datetime(run_at),
                        cron_expr=cron_expr,
                    )
                )
            except ReminderValidationError as exc:
                return f"创建提醒失败：{exc}"
            return _format_confirmation(created)

        return RegisteredTool(
            category=WRITE_TOOLS_CATEGORY,
            name=create_reminder_tool.name,
            description="创建一次性或重复提醒，重复提醒使用 cron 表达式并限制为不高于每 8 小时一次。",
            prompt_hint="当用户要求未来某个时间或某种重复规则提醒他做事时，使用这个小工具。",
            is_core=False,
            tool=create_reminder_tool,
        )


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized_value = value.strip()
    if normalized_value == "":
        return None
    return datetime.fromisoformat(normalized_value)


def _format_confirmation(created: CreatedReminder) -> str:
    schedule = created.schedule
    if schedule.run_at is not None:
        return f"好的，我会在 {schedule.run_at.astimezone().isoformat()} 提醒你：{schedule.reminder_text}。"
    return f"好的，我已经创建 cron 重复提醒：{schedule.reminder_text}。"
