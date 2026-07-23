from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent.context.tools.models import ToolCategory

WRITE_TOOLS_CATEGORY = ToolCategory(
    name="write_tools",
    title="写入类",
    description="用于创建、更新或写入会改变系统状态的数据，也包括创建未来执行的定时提醒。",
)


class CreateReminderToolInput(BaseModel):
    """创建提醒工具的输入参数。"""

    reminder_text: str = Field(description="提醒内容，例如 提交日报。")
    run_at: str | None = Field(default=None, description="一次性提醒时间，ISO 8601 字符串。")
    cron_expr: str | None = Field(default=None, description="重复提醒的 cron 表达式，例如 0 3 * * 2 或 0 */8 * * *。")
