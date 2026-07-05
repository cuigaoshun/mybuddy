from __future__ import annotations

from app.agent.context.tools.models import ToolCategory


def build_tool_selector_description(categories: tuple[ToolCategory, ...]) -> str:
    lines = [
        "当你判断当前问题需要调用工具时，先用这个工具选择最匹配的工具大类。",
        "如果不需要工具，就不要调用它，直接正常回复。",
        "只能从下面这些工具大类中选择一个 category_name：",
    ]
    for index, category in enumerate(categories, start=1):
        lines.append(f"{index}. {category.title}（{category.name}）：{category.description}")
    return "\n".join(lines)
