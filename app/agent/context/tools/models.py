from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.memory.models import HistorySearchResult

# 统一约束工具大类名称，避免上下游各写一套字符串。
ToolCategoryName = Literal["history_tools", "memory_tools", "web_search_tools"]


@dataclass(frozen=True, slots=True)
class ToolCategory:
    """表示一个可供模型选择的工具大类。"""

    # 工具大类的内部稳定名称。
    name: ToolCategoryName
    # 工具大类给模型展示的中文标题。
    title: str
    # 工具大类的功能描述。
    description: str


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """表示单个工具的完整规格定义。"""

    # 当前工具所属的工具大类。
    category: ToolCategory
    # 工具的唯一名称。
    name: str
    # 工具用途描述。
    description: str
    # 给模型的简短提示，说明何时应使用该工具。
    prompt_hint: str
    # 实际绑定给 LangChain / LangGraph 的工具对象。
    tool: BaseTool


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    """表示执行工具时必须携带的会话上下文。"""

    # 当前用户 ID。
    user_id: str
    # 当前平台类型。
    im_type: str
    # 当前会话 chat_id。
    chat_id: str


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    """表示一次工具调用后的标准化执行结果。"""

    # 本次执行的工具名称。
    tool_name: str
    # 本次工具调用在模型侧的调用 ID。
    tool_call_id: str
    # 返回给模型阅读的文本结果。
    text: str
    # 返回给上下文构建器做结构化处理的结果集合。
    structured_results: tuple[HistorySearchResult, ...]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """把工具规格与真正执行函数绑定在一起。"""

    # 工具的静态规格信息。
    spec: ToolSpec
    # 工具的执行入口，负责把参数和上下文转成统一执行结果。
    execute: Callable[[dict[str, object], ToolCallContext, str], ToolExecutionResult]


class SearchHistoryToolInput(BaseModel):
    """历史查询工具的输入参数模型。"""

    # 要搜索的历史话题或关键词。
    text: str = Field(default="", description="要查询的历史话题、关键词或句子。")
    # 查询起始时间，使用 ISO 8601 字符串表示。
    start_time: str | None = Field(default=None, description="开始时间，ISO 8601 字符串，例如 2026-07-01T00:00:00+08:00。")
    # 查询结束时间，使用 ISO 8601 字符串表示。
    end_time: str | None = Field(default=None, description="结束时间，ISO 8601 字符串，例如 2026-07-05T23:59:59+08:00。")


class WebSearchToolInput(BaseModel):
    """网页搜索工具的输入参数模型。"""

    # 要搜索的网页查询语句。
    query: str = Field(min_length=1, description="要检索的网页搜索查询语句。")
    # 返回结果条数，可为空时回退到系统默认值。
    limit: int | None = Field(default=None, ge=1, le=10, description="返回结果条数，默认使用系统配置。")


class SelectToolCategoryInput(BaseModel):
    """工具大类选择器的输入参数模型。"""

    # 当前选择的工具大类名称。
    category_name: ToolCategoryName = Field(description="选中的工具大类名称。")


def parse_tool_datetime(value: str | None) -> datetime | None:
    # 空值直接返回 None。
    if value is None:
        return None
    # 先去掉前后空白。
    normalized_value = value.strip()
    # 空字符串同样视为未传。
    if not normalized_value:
        return None
    # 用标准 ISO 8601 解析时间字符串。
    return datetime.fromisoformat(normalized_value)


def extract_tool_arguments(tool_args: object) -> dict[str, object]:
    # 只有字典参数才视为合法工具参数。
    if not isinstance(tool_args, dict):
        return {}
    # 返回浅拷贝后的参数字典，避免上游对象被原地污染。
    return dict(tool_args)
