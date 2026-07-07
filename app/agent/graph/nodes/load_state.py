from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def load_state_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    # 当前节点不依赖共享上下文对象。
    del context
    # 用平台、会话和发送者拼一个稳定线程标识。
    thread_id = f"{state.message.im_type}:{state.message.chat_id}:{state.message.sender_id}"
    # 同时把原始消息文本裁成 canonical_query，供后续节点统一使用。
    return state.model_copy(update={"thread_id": thread_id, "canonical_query": state.message.text.strip()})
