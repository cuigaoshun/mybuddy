from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.agent.context.tools.models import ToolCategory

# 定义历史检索工具所属的大类信息。
HISTORY_TOOLS_CATEGORY = ToolCategory(
    name="history_tools",
    title="历史检索类",
    description="用于查询当前会话中更早的对话记录，适合处理“之前聊过什么”“上次提过什么”这类问题。",
)


class SearchHistoryToolInput(BaseModel):
    """历史查询工具的输入参数模型。"""

    # 要搜索的历史话题或关键词。
    text: str = Field(default="", description="要查询的历史话题、关键词或句子。")
    # 查询起始时间，使用 ISO 8601 字符串表示。
    start_time: str | None = Field(default=None, description="开始时间，ISO 8601 字符串，例如 2026-07-01T00:00:00+08:00。")
    # 查询结束时间，使用 ISO 8601 字符串表示。
    end_time: str | None = Field(default=None, description="结束时间，ISO 8601 字符串，例如 2026-07-05T23:59:59+08:00。")


def parse_tool_datetime(value: str | None) -> datetime | None:
    """把工具里的可选时间字符串解析成 datetime。"""

    # 未传值时直接返回空。
    if value is None:
        return None
    # 先去掉字符串两端空白。
    normalized_value = value.strip()
    # 空字符串同样视为未传。
    if not normalized_value:
        return None
    # 按 ISO 8601 解析时间。
    return datetime.fromisoformat(normalized_value)
