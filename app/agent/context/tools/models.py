from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.memory.models import HistorySearchResult

ToolCategoryName = Literal["history_tools", "memory_tools", "web_search_tools"]


@dataclass(frozen=True, slots=True)
class ToolCategory:
    name: ToolCategoryName
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class ToolSpec:
    category: ToolCategory
    name: str
    description: str
    prompt_hint: str
    tool: BaseTool


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    user_id: str
    im_type: str
    chat_id: str


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    tool_name: str
    tool_call_id: str
    text: str
    structured_results: tuple[HistorySearchResult, ...]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    spec: ToolSpec
    execute: Callable[[dict[str, object], ToolCallContext, str], ToolExecutionResult]


class SearchHistoryToolInput(BaseModel):
    text: str = Field(default="", description="要查询的历史话题、关键词或句子。")
    start_time: str | None = Field(default=None, description="开始时间，ISO 8601 字符串，例如 2026-07-01T00:00:00+08:00。")
    end_time: str | None = Field(default=None, description="结束时间，ISO 8601 字符串，例如 2026-07-05T23:59:59+08:00。")


class WebSearchToolInput(BaseModel):
    query: str = Field(min_length=1, description="要检索的网页搜索查询语句。")
    limit: int | None = Field(default=None, ge=1, le=10, description="返回结果条数，默认使用系统配置。")


class SelectToolCategoryInput(BaseModel):
    category_name: ToolCategoryName = Field(description="选中的工具大类名称。")


def parse_tool_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized_value = value.strip()
    if not normalized_value:
        return None
    return datetime.fromisoformat(normalized_value)


def extract_tool_arguments(tool_args: object) -> dict[str, object]:
    if not isinstance(tool_args, dict):
        return {}
    return dict(tool_args)
