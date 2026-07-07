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
from app.memory.models import ConversationHistoryQuery, HistorySearchResult
from app.memory.service import ConversationMemoryService

# 定义历史查询工具所属的大类元信息。
HISTORY_TOOLS_CATEGORY = ToolCategory(
    name="history_tools",
    title="历史检索类",
    description="用于查询当前会话中更早的对话记录，适合处理“之前聊过什么”“上次提过什么”这类问题。",
)


def build_history_tool_definition(conversation_memory_service: ConversationMemoryService) -> ToolDefinition:
    # 定义仅供模型发起调用意图的历史检索工具壳。
    @tool("search_history", args_schema=SearchHistoryToolInput)
    def search_history_tool(text: str = "", start_time: str | None = None, end_time: str | None = None) -> str:
        """查询当前会话指定时间范围内的历史消息，可结合关键词与语义召回。"""
        # 真实执行统一交给图内工具执行器完成。
        del text, start_time, end_time
        return "请通过图内工具执行器调用该工具。"

    # 先组装历史工具规格信息。
    spec = ToolSpec(
        category=HISTORY_TOOLS_CATEGORY,
        name="search_history",
        description="按关键词、语义和时间范围查询当前会话的历史消息。",
        prompt_hint="当你需要更久以前的对话证据时，使用这个小工具。",
        tool=search_history_tool,
    )

    def execute(tool_args: dict[str, object], call_context: ToolCallContext, tool_call_id: str) -> ToolExecutionResult:
        # 根据工具参数执行历史检索，并把结构化结果和展示文本一起返回。
        # 读取关键词或查询句子。
        text = tool_args.get("text")
        # 读取开始时间参数。
        start_time = tool_args.get("start_time")
        # 读取结束时间参数。
        end_time = tool_args.get("end_time")
        # 调用记忆服务执行历史查询。
        search_results = tuple(
            conversation_memory_service.search_history(
                ConversationHistoryQuery(
                    # 透传当前用户 ID。
                    user_id=call_context.user_id,
                    # 透传当前平台类型。
                    im_type=call_context.im_type,
                    # 透传当前会话 ID。
                    chat_id=call_context.chat_id,
                    # 非字符串参数降级为空查询。
                    text=text if isinstance(text, str) else "",
                    # 尝试解析开始时间。
                    start_time=parse_tool_datetime(start_time if isinstance(start_time, str) else None),
                    # 尝试解析结束时间。
                    end_time=parse_tool_datetime(end_time if isinstance(end_time, str) else None),
                    # 当前固定最多取 5 条结果。
                    limit=5,
                )
            )
        )
        # 把历史查询结果包装成统一工具结果。
        return ToolExecutionResult(
            tool_name=spec.name,
            tool_call_id=tool_call_id,
            text=_format_history_results(search_results),
            structured_results=search_results,
        )

    # 返回最终的历史工具定义对象。
    return ToolDefinition(spec=spec, execute=execute)


def _format_history_results(results: tuple[HistorySearchResult, ...]) -> str:
    # 没有命中结果时返回固定空文案。
    if not results:
        return "未找到符合条件的历史消息。"

    # 先写标题行。
    lines = ["以下是命中的历史消息片段："]
    # 再按顺序展开每个结果。
    for index, result in enumerate(results, start=1):
        # 兼容性读取底层记录对象。
        record = getattr(result, "record", None)
        # 没有记录对象就跳过。
        if record is None:
            continue
        # 根据消息类型转成中文角色名。
        role_name = "用户" if record.message_type == 0 else "助手"
        # 计算命中来源描述。
        source = _build_history_match_source(result)
        # 只读取一期 text 字段。
        text_value = record.content.get("text")
        # 非字符串内容统一降级为空串。
        content = text_value.strip() if isinstance(text_value, str) else ""
        # 没有可读内容时直接跳过。
        if not content:
            continue
        # 拼装一条结果展示文本。
        lines.append(
            f"{index}. 时间：{record.message_time.isoformat()}｜角色：{role_name}｜来源：{source}｜内容：{content}"
        )
    # 如果标题之外没有有效内容，仍返回空结果文案。
    if len(lines) == 1:
        return "未找到符合条件的历史消息。"
    # 返回格式化后的多行文本。
    return "\n".join(lines)


def _build_history_match_source(result: HistorySearchResult) -> str:
    # 读取全文命中标记。
    matched_by_text = bool(getattr(result, "matched_by_text", False))
    # 读取语义命中标记。
    matched_by_vector = bool(getattr(result, "matched_by_vector", False))
    # 同时命中全文和语义时返回组合标签。
    if matched_by_text and matched_by_vector:
        return "全文+语义"
    # 仅全文命中时返回全文。
    if matched_by_text:
        return "全文"
    # 仅语义命中时返回语义。
    if matched_by_vector:
        return "语义"
    # 两者都不是时，视为时间窗结果。
    return "时间窗"
