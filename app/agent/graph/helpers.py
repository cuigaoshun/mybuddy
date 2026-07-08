from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agent.context.tools.models import ToolCategoryName

from .runtime import GraphRuntimeContext
from .state import ReplyState


def extract_selected_category(reply: AIMessage) -> ToolCategoryName | None:
    # 逐个检查模型返回的 tool call。
    for tool_call in getattr(reply, "tool_calls", []) or []:
        # 只关心工具大类选择器本身。
        if tool_call.get("name") != "select_tool_category":
            continue
        # 读取当前工具调用参数。
        tool_args = tool_call.get("args")
        # 非字典参数直接跳过，避免异常结构污染流程。
        if not isinstance(tool_args, dict):
            continue
        # 提取被模型选中的工具大类名称。
        category_name = tool_args.get("category_name")
        # 只接受当前仓库已注册的非核心工具大类。
        if category_name in {"history_tools", "memory_tools", "web_search_tools"}:
            return category_name
    # 没有选出合法工具大类时返回空。
    return None


def has_non_selector_tool_call(reply: AIMessage) -> bool:
    # 遍历模型返回的全部工具调用。
    for tool_call in getattr(reply, "tool_calls", []) or []:
        # 读取当前工具名称。
        tool_name = tool_call.get("name")
        # 只要存在非 selector 的工具调用，就说明模型要直接执行真实工具。
        if isinstance(tool_name, str) and tool_name != "select_tool_category":
            return True
    # 否则说明当前轮没有真实工具调用。
    return False


def invoke_model(model, messages: list[BaseMessage]) -> AIMessage:
    # 用当前消息序列直接调用模型。
    return model.invoke(messages)


def build_selector_messages(state: ReplyState, context: GraphRuntimeContext) -> list[BaseMessage]:
    # selector 阶段当前直接复用标准聊天消息序列。
    return build_chat_messages(state=state, context=context)


def build_chat_messages(state: ReplyState, context: GraphRuntimeContext) -> list[BaseMessage]:
    # 如果图状态里已经有累计消息，优先直接复用，避免重复格式化。
    if state.messages:
        return list(state.messages)
    # 如果当前轮还没构建上下文包，就退化成只发送用户原始消息。
    if state.context_bundle is None:
        return [HumanMessage(content=state.message.text)]
    # 先把结构化上下文格式化成完整消息序列。
    formatted_messages = list(context.context_formatter.format(state.context_bundle))
    # 再根据模型上下文预算裁剪消息总长度。
    trimmed_messages = context.context_budgeter.trim_messages(tuple(formatted_messages))
    # 返回可继续追加和传递的消息列表。
    return list(trimmed_messages)
