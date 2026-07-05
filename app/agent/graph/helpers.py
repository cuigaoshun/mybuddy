from __future__ import annotations

from loguru import logger
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from app.agent.context.tools.models import ToolCategoryName
from app.agent.util import extract_reply_text, format_messages_for_log


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
        if category_name in {"history_tools", "memory_tools", "web_search_tools"}:
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


def has_non_category_tool_call(reply: AIMessage) -> bool:
    for tool_call in getattr(reply, "tool_calls", []) or []:
        tool_name = tool_call.get("name")
        if isinstance(tool_name, str) and tool_name != "select_tool_category":
            return True
    return False


def invoke_model(model, messages: list, bound_tools_summary: str) -> AIMessage:
    """统一封装模型调用：把绑定工具摘要注入上下文并记录日志。"""

    effective_messages = _inject_bound_tools_context(messages, bound_tools_summary)
    logger.info("当前绑定工具: {}", bound_tools_summary)
    logger.info("请求模型提示词:\n{}", format_messages_for_log(effective_messages))
    reply = model.invoke(effective_messages)
    logger.info(
        "模型回复: text={} tool_calls={}",
        extract_reply_text(reply),
        getattr(reply, "tool_calls", []),
    )
    return reply


def _inject_bound_tools_context(messages: list[BaseMessage], bound_tools_summary: str) -> list[BaseMessage]:
    normalized_summary = bound_tools_summary.strip()
    if normalized_summary in {"", "[]"}:
        return messages

    tool_context_line = f"当前绑定工具：{normalized_summary}"
    if messages and isinstance(messages[0], SystemMessage):
        first_message = messages[0]
        merged_content = f"{first_message.content}\n\n{tool_context_line}"
        return [SystemMessage(content=merged_content), *messages[1:]]
    return [SystemMessage(content=tool_context_line), *messages]
