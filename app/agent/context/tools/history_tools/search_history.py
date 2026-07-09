from langchain_core.tools import tool
from langchain.tools import ToolRuntime

from app.agent.context.tools.models import RegisteredTool, ToolDefinition
from app.agent.context.tools.tool_runtime import get_reply_state
from app.memory.models import ConversationHistoryQuery, HistorySearchResult
from app.memory.service import ConversationMemoryService

from .models import HISTORY_TOOLS_CATEGORY, SearchHistoryToolInput, parse_tool_datetime


class HistoryToolDefinition(ToolDefinition):
    """统一封装历史查询工具的构建逻辑。"""

    @classmethod
    def build(cls, conversation_memory_service: ConversationMemoryService) -> RegisteredTool:
        """基于记忆服务构建历史查询工具注册条目。"""

        @tool("search_history", args_schema=SearchHistoryToolInput)
        def search_history_tool(
            runtime: ToolRuntime,
            text: str = "",
            start_time: str | None = None,
            end_time: str | None = None,
        ) -> str:
            """查询当前会话指定时间范围内的历史消息，可结合关键词与语义召回。"""

            # 直接从 ToolRuntime 读取当前图状态。
            state = get_reply_state(runtime)
            if state is None:
                return "当前缺少会话状态，无法执行历史查询。"
            # 基于当前会话执行历史检索。
            search_results = tuple(
                conversation_memory_service.search_history(
                    ConversationHistoryQuery(
                        user_id=state.message.sender_id,
                        im_type=state.message.im_type,
                        chat_id=state.message.chat_id,
                        text=text,
                        start_time=parse_tool_datetime(start_time),
                        end_time=parse_tool_datetime(end_time),
                        limit=5,
                    )
                )
            )
            # 把查询结果格式化成纯文本返回给模型。
            return _format_history_results(search_results)

        # 直接返回带完整元信息的注册条目。
        return RegisteredTool(
            category=HISTORY_TOOLS_CATEGORY,
            name=search_history_tool.name,
            description="按关键词、语义和时间范围查询当前会话的历史消息。",
            prompt_hint="当你需要更久以前的对话证据时，使用这个小工具。",
            is_core=True,
            tool=search_history_tool,
        )


def _format_history_results(results: tuple[HistorySearchResult, ...]) -> str:
    """把历史查询结果格式化成模型可直接阅读的文本。"""

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
        # 只读取一期 text 字段。
        text_value = record.content.get("text")
        # 非字符串内容统一降级为空串。
        content = text_value.strip() if isinstance(text_value, str) else ""
        # 没有可读内容时直接跳过。
        if not content:
            continue
        # 拼装一条结果展示文本。
        lines.append(f"{index}. 时间：{record.message_time.isoformat()}｜角色：{role_name}｜内容：{content}")
    # 如果标题之外没有有效内容，仍返回空结果文案。
    if len(lines) == 1:
        return "未找到符合条件的历史消息。"
    # 返回格式化后的多行文本。
    return "\n".join(lines)
