from __future__ import annotations

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict

from app.agent.context.models import ContextBundle
from app.agent.context.tools.models import ToolCategoryName
from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo


class ReplyState(BaseModel):
    """回复流程在图内流转的统一状态。"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # 当前这次进入图的用户消息。
    message: IncomingChatMessage
    # 当前会话的轻量元信息快照。
    session_info: ChatSessionInfo
    # 上下文构建层产出的完整上下文包。
    context_bundle: ContextBundle
    # 图完成后输出给外部的最终回复文本。
    reply_text: str | None = None
    # 当前轮送给模型的 message 序列。
    messages: tuple[BaseMessage, ...] = ()
    # 第一阶段工具分类选择器选中的工具大类。
    selected_tool_category: ToolCategoryName | None = None
    # 是否已经完成首阶段 select_tool 决策。
    tool_selection_completed: bool = False
    # 首阶段是否需要在工具执行后刷新上下文消息。
    refresh_after_tool: bool = False
