from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain_core.tools import tool
from langgraph.types import Command

from app.agent.graph.main_graph.constants import SELECT_TOOL_CATEGORY_TOOL_NAME

from .models import SelectToolCategoryInput, ToolCategory, ToolCategoryName, ToolCategorySelection
from .prompts import build_tool_selector_description


def build_category_selector_tool(categories: tuple[ToolCategory, ...]) -> BaseTool:
    # 先把当前允许模型选择的非核心工具大类收成集合，便于后续快速过滤非法值。
    allowed_category_names = {category.name for category in categories}
    selector_description = build_tool_selector_description(categories)

    # 定义一个只负责声明“我想选哪个大类”的工具壳。
    @tool(SELECT_TOOL_CATEGORY_TOOL_NAME, args_schema=SelectToolCategoryInput)
    def select_tool_category_tool(category_names: list[ToolCategoryName]) -> Command:
        """当你判断需要使用工具时，先选择最匹配的工具大类。"""
        # 先按当前运行时允许的大类过滤并去重，避免模型传入无效或重复类别。
        selected_category_names = _normalize_category_names(category_names, allowed_category_names)
        # 如果最终没有合法类别，就显式写回 None，表示后续只开放核心工具。
        if not selected_category_names:
            return Command(update={"selected_tool_category": None})
        # 正常情况下把合法类别元组写回图状态，供后续工具暴露与执行节点使用。
        return Command(update={"selected_tool_category": selected_category_names})

    select_tool_category_tool.description = selector_description

    # 返回构建好的工具选择器。
    return select_tool_category_tool


def _normalize_category_names(
    category_names: list[ToolCategoryName],
    allowed_category_names: set[ToolCategoryName],
) -> ToolCategorySelection:
    """过滤非法值并按原顺序去重，得到最终工具大类选择结果。"""

    # 这里保留顺序是为了尽量尊重模型给出的优先级，虽然当前执行层主要关心“开放哪些类”。
    normalized_category_names: list[ToolCategoryName] = []
    for category_name in category_names:
        # 不在当前允许集合里的类别直接丢弃，避免模型越权开放未注册工具类。
        if category_name not in allowed_category_names:
            continue
        # 重复类别只保留第一次出现的位置，避免状态里出现冗余值。
        if category_name in normalized_category_names:
            continue
        normalized_category_names.append(category_name)
    return tuple(normalized_category_names)
