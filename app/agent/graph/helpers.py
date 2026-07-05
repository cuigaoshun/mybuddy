from __future__ import annotations

from langchain_core.messages import AIMessage

from app.agent.context.tools.models import ToolCategoryName
from app.agent.util import extract_reply_text


def extract_selected_category(reply: AIMessage) -> ToolCategoryName | None:
    """从 selector tool 的 tool_calls 里提取被选中的工具大类。"""

    # 第一阶段只关心 selector tool 是否返回了合法的大类选择。
    for tool_call in getattr(reply, "tool_calls", []) or []:
        # 只解析大类选择工具，忽略其他 tool call。
        if tool_call.get("name") != "select_tool_category":
            continue
        tool_args = tool_call.get("args")
        # 参数结构不对时直接跳过，避免污染后续状态。
        if not isinstance(tool_args, dict):
            continue
        category_name = tool_args.get("category_name")
        # 目前仅接受仓库里声明过的合法工具大类。
        if category_name in {"history_tools", "memory_tools"}:
            return category_name
    return None


def extract_selector_reply_text(reply: AIMessage) -> str | None:
    """从 selector 阶段回复里提取可直接结束流程的最终文本。"""

    if getattr(reply, "tool_calls", None):
        return None
    reply_text = extract_reply_text(reply).strip()
    if not reply_text:
        return None
    return reply_text
