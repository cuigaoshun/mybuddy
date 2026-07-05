from __future__ import annotations

from langchain_core.tools import tool

from .models import (
    SearchHistoryToolInput,
    ToolCallContext,
    ToolCategory,
    ToolDefinition,
    ToolExecutionResult,
    ToolSpec,
    parse_tool_datetime,
)
from app.memory.models import ConversationHistoryQuery
from app.memory.service import ConversationMemoryService

HISTORY_TOOLS_CATEGORY = ToolCategory(
    name="history_tools",
    title="历史检索类",
    description="用于查询当前会话中更早的对话记录，适合处理“之前聊过什么”“上次提过什么”这类问题。",
)


def build_history_tool_definition(conversation_memory_service: ConversationMemoryService) -> ToolDefinition:
    @tool("search_history", args_schema=SearchHistoryToolInput)
    def search_history_tool(text: str = "", start_time: str | None = None, end_time: str | None = None) -> str:
        """查询当前会话指定时间范围内的历史消息，可结合关键词与语义召回。"""
        return "请通过图内工具执行器调用该工具。"

    spec = ToolSpec(
        category=HISTORY_TOOLS_CATEGORY,
        name="search_history",
        description="按关键词、语义和时间范围查询当前会话的历史消息。",
        prompt_hint="当你需要更久以前的对话证据时，使用这个小工具。",
        tool=search_history_tool,
    )

    def execute(tool_args: dict[str, object], call_context: ToolCallContext, tool_call_id: str) -> ToolExecutionResult:
        # 根据工具参数执行历史检索，并把结构化结果和展示文本一起返回。
        text = tool_args.get("text")
        start_time = tool_args.get("start_time")
        end_time = tool_args.get("end_time")
        search_results = tuple(
            conversation_memory_service.search_history(
                ConversationHistoryQuery(
                    user_id=call_context.user_id,
                    im_type=call_context.im_type,
                    chat_id=call_context.chat_id,
                    text=text if isinstance(text, str) else "",
                    start_time=parse_tool_datetime(start_time if isinstance(start_time, str) else None),
                    end_time=parse_tool_datetime(end_time if isinstance(end_time, str) else None),
                    limit=5,
                )
            )
        )
        return ToolExecutionResult(
            tool_name=spec.name,
            tool_call_id=tool_call_id,
            text=_format_history_results(search_results),
            structured_results=search_results,
        )

    return ToolDefinition(spec=spec, execute=execute)


def _format_history_results(results: tuple[object, ...]) -> str:
    if not results:
        return "未找到符合条件的历史消息。"

    lines = ["以下是命中的历史消息片段："]
    for index, result in enumerate(results, start=1):
        record = getattr(result, "record", None)
        if record is None:
            continue
        role_name = "用户" if record.message_type == 0 else "助手"
        source = _build_history_match_source(result)
        text_value = record.content.get("text")
        content = text_value.strip() if isinstance(text_value, str) else ""
        if not content:
            continue
        lines.append(
            f"{index}. 时间：{record.message_time.isoformat()}｜角色：{role_name}｜来源：{source}｜内容：{content}"
        )
    if len(lines) == 1:
        return "未找到符合条件的历史消息。"
    return "\n".join(lines)


def _build_history_match_source(result: object) -> str:
    matched_by_text = bool(getattr(result, "matched_by_text", False))
    matched_by_vector = bool(getattr(result, "matched_by_vector", False))
    if matched_by_text and matched_by_vector:
        return "全文+语义"
    if matched_by_text:
        return "全文"
    if matched_by_vector:
        return "语义"
    return "时间窗"
