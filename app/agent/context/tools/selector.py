from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain_core.tools import tool

from .models import SelectToolCategoryInput, ToolCategory
from .prompts import build_tool_selector_description


def build_category_selector_tool(categories: tuple[ToolCategory, ...]) -> BaseTool:
    # 先基于当前可用工具大类构建选择说明文本。
    selector_description = build_tool_selector_description(categories)

    # 定义一个只负责声明“我想选哪个大类”的工具壳。
    @tool("select_tool_category", args_schema=SelectToolCategoryInput)
    def select_tool_category_tool(category_name: str) -> str:
        """当你判断需要使用工具时，先选择最匹配的工具大类。"""
        # 真实返回内容是预先拼好的说明文本，而不是直接执行业务逻辑。
        del category_name
        return selector_description

    # 返回构建好的工具选择器。
    return select_tool_category_tool
