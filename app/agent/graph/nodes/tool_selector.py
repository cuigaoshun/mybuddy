from __future__ import annotations

from app.agent.context.tools.selector import build_category_selector_tool
from app.agent.util import extract_reply_text

from app.agent.graph.runtime import GraphRuntimeContext

from .. import helpers
from ..state import ReplyState


def tool_selector_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    """决定当前轮是直调核心工具、直接回复，还是先解锁某个非核心工具大类。"""

    # 先拿到全部核心工具对象。
    core_tools = context.tool_registry.list_core_tools()
    # 再构建一个只负责选工具大类的 selector 工具。
    selector_tool = build_category_selector_tool(context.tool_registry.list_non_core_categories())
    # selector 阶段绑定的是“工具大类选择器 + 全部核心工具”。
    selector_model = context.llm_provider.model().bind_tools([selector_tool, *core_tools])
    # 先拿到基础上下文消息序列，供核心工具直调分支后续继续使用。
    base_messages = helpers.build_chat_messages(state, context)
    # 再拿到 selector 专用消息序列。
    messages = helpers.build_selector_messages(state, context)
    # 调 selector 模型，判断这轮的工具策略。
    reply = helpers.invoke_model(model=selector_model, messages=messages)
    # 尝试从 tool_calls 里提取被选中的工具大类。
    selected_category = helpers.extract_selected_category(reply)
    # 如果除了 selector 之外还出现了真实工具调用，说明模型直接命中了核心工具。
    if helpers.has_non_selector_tool_call(reply):
        return state.model_copy(
            update={
                # 保留基础消息和 selector 回复，供核心工具节点直接继续执行。
                "messages": tuple([*base_messages, reply]),
                # 既然已经直调核心工具，就不再保留非核心工具类别。
                "selected_tool_category": None,
            }
        )
    # 尝试提取当前回复里的直接自然语言回答。
    direct_reply_text = _extract_direct_reply_text(reply)
    # 如果已经能直接回复用户，就在这里结束当前轮。
    if direct_reply_text is not None:
        return state.model_copy(update={"final_reply": direct_reply_text})
    # 其余情况只记录本轮选中的工具大类。
    return state.model_copy(update={"selected_tool_category": selected_category})


def _extract_direct_reply_text(reply) -> str | None:
    if getattr(reply, "tool_calls", None):
        return None
    reply_text = extract_reply_text(reply).strip()
    if reply_text == "":
        return None
    return reply_text
