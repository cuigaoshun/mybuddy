from __future__ import annotations

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict

from app.agent.context.models import ContextBundle
from app.agent.context.tools.models import ToolCategoryName
from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo


class ReplyState(BaseModel):
    """新回复图在图内流转的统一运行态。"""

    # 配置成不可变模型，强制节点通过 model_copy 返回新状态。
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # 当前进入图处理的用户消息。
    message: IncomingChatMessage
    # 当前消息所属的会话信息。
    session_info: ChatSessionInfo
    # 当前轮已经构建好的上下文总包。
    context_bundle: ContextBundle | None = None
    # 当前轮真正送进模型的消息序列，以及模型/工具回写后的消息累计。
    messages: tuple[BaseMessage, ...] = ()
    # 当前轮选中的工具大类；核心工具路径时为空。
    selected_tool_category: ToolCategoryName | None = None
    # 如果已经拿到最终自然语言回复，就写在这里并结束图。
    final_reply: str | None = None
    # 当前已经跑了多少轮工具回路。
    tool_round: int = 0
    # 允许的最大工具回路次数，用于避免无限循环。
    max_tool_rounds: int = 3
