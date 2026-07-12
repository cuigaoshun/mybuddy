from __future__ import annotations

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict

from app.agent.context.models import ContextBundle
from app.agent.context.tools.models import ToolCategorySelection
from app.agent.graph.constants import ToolPhase
from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo, MemoryRecord, RetrievedMemoryHit


class ReplyState(BaseModel):
    """新回复图在图内流转的统一运行态。"""

    # 配置成不可变模型，强制节点通过 model_copy 返回新状态。
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # 当前进入图处理的用户消息。
    message: IncomingChatMessage
    # 当前消息所属的会话信息。
    session_info: ChatSessionInfo
    recent_records: tuple[MemoryRecord, ...] = ()
    retrieved_memory_hits: tuple[RetrievedMemoryHit, ...] = ()
    reranked_memory_hits: tuple[RetrievedMemoryHit, ...] = ()
    # 当前轮已经构建好的上下文总包。
    context_bundle: ContextBundle | None = None
    # 当前轮真正送进模型的消息序列，以及模型/工具回写后的消息累计。
    messages: tuple[BaseMessage, ...] = ()
    # 当前轮已选中的非核心工具大类集合；为空时表示后续只允许核心工具。
    selected_tool_category: ToolCategorySelection | None = None
    # 当前工具流程所处阶段：等待 selector、selector 完成后回 chat_model，或常规空闲阶段。
    tool_phase: ToolPhase = ToolPhase.AWAIT_SELECTOR
    # 如果已经拿到最终自然语言回复，就写在这里并结束图。
    final_reply: str | None = None
    # 当前已经跑了多少轮工具回路。
    tool_round: int = 0
    # 允许的最大工具回路次数，用于避免无限循环。
    max_tool_rounds: int = 10
