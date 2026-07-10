from __future__ import annotations

from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def retrieve_memory_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    """召回与当前用户输入最相关的长期记忆命中结果。"""

    return state.model_copy(
        update={
            # 当前节点只负责原始召回，不在这里做重排和上下文组装。
            "retrieved_memory_hits": tuple(
                # 先按当前用户文本做向量召回，后续再交给 rerank 节点裁剪数量。
                context.services.conversation_memory_service.retrieve_memory_hits(
                    user_id=state.message.sender_id,
                    im_type=state.message.im_type,
                    chat_id=state.message.chat_id,
                    query_text=state.message.text,
                    limit=10,
                    exclude_message_ids=(state.message.message_id,),
                )
            ),
        }
    )
