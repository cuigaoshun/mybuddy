from __future__ import annotations

from app.agent.context.tools.models import ToolCategory, ToolSpec

BASE_TOOL_POLICY_PROMPT = """工具使用约束：
1. 先判断需要哪一个工具大类，再选择该大类下的具体小工具。
2. 只有在当前上下文不足以回答、且工具能显著补充事实时，才调用工具。
3. 工具返回的结果是参考材料，不要把历史片段误说成刚刚发生的对话。"""

CATEGORY_SELECTOR_PROMPT = """工具大类选择流程：
1. 先判断当前问题是否真的需要工具；如果不需要，就直接回答。
2. 如果需要工具，先在脑中明确选择一个最匹配的工具大类。
3. 只有在选定工具大类后，才从该大类下选择一个具体小工具。
4. 不要跨大类随意调用小工具。
5. 工具调用完成后，要基于返回结果继续回答，而不是只复述工具输出。"""


def build_tool_selector_prompt(categories: tuple[ToolCategory, ...]) -> str | None:
    if not categories:
        return None

    lines = [CATEGORY_SELECTOR_PROMPT, "", "可供选择的工具大类："]
    for index, category in enumerate(categories, start=1):
        lines.append(f"{index}. {category.title}（{category.name}）：{category.description}")
    return "\n".join(lines)


def build_tool_category_prompt(categories: tuple[ToolCategory, ...], tools: tuple[ToolSpec, ...]) -> str | None:
    if not categories:
        return None

    tool_specs_by_category: dict[str, list[ToolSpec]] = {}
    for tool_spec in tools:
        tool_specs_by_category.setdefault(tool_spec.category.name, []).append(tool_spec)

    lines = [BASE_TOOL_POLICY_PROMPT, "", "当前可用工具大类："]
    for index, category in enumerate(categories, start=1):
        lines.append(f"{index}. {category.title}（{category.name}）：{category.description}")
        for tool_spec in tool_specs_by_category.get(category.name, []):
            lines.append(f"   - 小工具 `{tool_spec.name}`：{tool_spec.prompt_hint}")
    return "\n".join(lines)
