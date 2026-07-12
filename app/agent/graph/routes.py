from __future__ import annotations

from langchain_core.messages import AIMessage

from .constants import GraphNodes, SELECT_TOOL_CATEGORY_TOOL_NAME, ToolPhase
from .state import ReplyState


def route_after_chat_model(state: ReplyState) -> GraphNodes:
    """根据 chat_model 的输出决定下一跳。"""

    # 倒序找到最近一条 AIMessage，避免末尾恰好不是 AIMessage 时误判路由。
    last_ai_message = next(
        (
            message
            for message in reversed(state.messages)
            if isinstance(message, AIMessage)
        ),
        None,
    )
    # 没有任何 AI 回复时，说明当前轮无法继续走工具分支，直接结束。
    if last_ai_message is None:
        return GraphNodes.END
    # selector 决策轮下，只要看到了 selector 调用，就先进入 selector 消费节点。
    if state.tool_phase == ToolPhase.AWAIT_SELECTOR and _has_selector_tool_call(last_ai_message):
        return GraphNodes.APPLY_TOOL_SELECTION
    # 走到这里说明当前不是 selector 消费路径；如果没有任何 tool_call，本轮就可以直接结束。
    # 最近一条 AI 回复没有 tool_call 时，说明本轮已经得到最终自然语言回复。
    if not last_ai_message.tool_calls:
        return GraphNodes.END
    # 只要当前轮存在真实工具调用，就统一进入工具执行节点。
    return GraphNodes.EXECUTE_TOOLS


def route_after_tool_selection(state: ReplyState) -> GraphNodes:
    """根据 selector 消费结果决定下一跳。"""

    # selector-only 路径会把阶段置为 AWAIT_POST_SELECTOR_CHAT，表示要带着新开放的工具集再回一次 chat_model。
    if state.tool_phase == ToolPhase.AWAIT_POST_SELECTOR_CHAT:
        return GraphNodes.CHAT_MODEL
    # mixed 路径下，selector 节点会把最后一条 AIMessage 改写成只含真实工具调用的版本；
    # 这里再次读取最新 AIMessage，决定是否进入 execute_tools。
    last_ai_message = next(
        (
            message
            for message in reversed(state.messages)
            if isinstance(message, AIMessage)
        ),
        None,
    )
    # 理论上 mixed 路径应至少保留一个真实工具调用；如果没有，则安全结束当前轮。
    if last_ai_message is None or not last_ai_message.tool_calls:
        return GraphNodes.END
    # 剩下的情况说明 selector 已被消费干净，最后一条 AIMessage 里只剩真实工具调用，进入执行节点即可。
    return GraphNodes.EXECUTE_TOOLS


def _has_selector_tool_call(message: AIMessage) -> bool:
    # 这里只做非常薄的一层识别：当前 AIMessage 里只要出现 selector 工具名，
    # selector 决策轮就应该优先转交给独立 selector node 处理。
    for tool_call in message.tool_calls:
        if tool_call.get("name") == SELECT_TOOL_CATEGORY_TOOL_NAME:
            return True
    return False
