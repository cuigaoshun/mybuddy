from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain_core.tools import tool
from langgraph.types import Command

from .models import SelectToolCategoryInput, ToolCategory, ToolCategoryName, ToolCategorySelection


def build_category_selector_tool(categories: tuple[ToolCategory, ...]) -> BaseTool:
    allowed_category_names = {category.name for category in categories}

    # 定义一个只负责声明“我想选哪个大类”的工具壳。
    @tool("select_tool_category", args_schema=SelectToolCategoryInput)
    def select_tool_category_tool(category_names: list[ToolCategoryName]) -> Command:
        """当你判断需要使用工具时，先选择最匹配的工具大类。"""
        selected_category_names = _normalize_category_names(category_names, allowed_category_names)
        if not selected_category_names:
            return Command(update={"selected_tool_category": None})
        return Command(update={"selected_tool_category": selected_category_names})

    # 返回构建好的工具选择器。
    return select_tool_category_tool


def _normalize_category_names(
    category_names: list[ToolCategoryName],
    allowed_category_names: set[ToolCategoryName],
) -> ToolCategorySelection:
    """过滤非法值并按原顺序去重，得到最终工具大类选择结果。"""

    normalized_category_names: list[ToolCategoryName] = []
    for category_name in category_names:
        if category_name not in allowed_category_names:
            continue
        if category_name in normalized_category_names:
            continue
        normalized_category_names.append(category_name)
    return tuple(normalized_category_names)
