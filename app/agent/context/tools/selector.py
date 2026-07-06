from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain_core.tools import tool

from .models import SelectToolCategoryInput, ToolCategory
from .prompts import build_tool_selector_description


def build_category_selector_tool(categories: tuple[ToolCategory, ...]) -> BaseTool:
    selector_description = build_tool_selector_description(categories)

    @tool("select_tool_category", args_schema=SelectToolCategoryInput)
    def select_tool_category_tool(category_name: str) -> str:
        """当你判断需要使用工具时，先选择最匹配的工具大类。"""
        return selector_description

    return select_tool_category_tool
