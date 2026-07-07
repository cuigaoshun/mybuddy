from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext
from app.agent.util import extract_reply_text

from ..helpers import build_chat_messages, invoke_model
from ..state import ReplyState


def chat_model_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    # 先构建主模型阶段真正要消费的消息序列。
    messages = build_chat_messages(state, context)
    # 如果当前轮已经展开出可用工具，就把这些工具绑定给模型。
    if state.active_tool_specs:
        model = context.llm_provider.model().bind_tools([tool_spec.tool for tool_spec in state.active_tool_specs])
        # 同步记录绑定工具名，方便日志里观察模型当前可调用哪些工具。
        bound_tool_names = state.active_tool_names
    else:
        # 没有任何工具可用时，就直接使用裸模型自然回答。
        model = context.llm_provider.model()
        # 这时绑定工具名列表为空。
        bound_tool_names = ()
    # 调主模型，得到这一轮的回复或 tool_calls。
    reply = invoke_model(model=model, messages=messages, bound_tool_names=bound_tool_names)
    # 把输入消息和模型回复一起写入状态消息序列。
    updated_messages = tuple([*messages, reply])
    # 有 tool_calls 就说明还没结束；没有 tool_calls 才把自然语言落成 final_reply。
    final_reply = None if getattr(reply, "tool_calls", None) else extract_reply_text(reply)
    # 返回更新后的消息序列和可能的最终回复。
    return state.model_copy(
        update={
            "messages": updated_messages,
            "final_reply": final_reply,
        }
    )
