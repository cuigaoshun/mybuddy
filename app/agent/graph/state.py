from __future__ import annotations

from typing import Literal

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ConfigDict

from app.agent.context.models import ContextBundle
from app.agent.context.tools.models import ToolCategoryName, ToolExecutionResult, ToolSpec
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
    # 当前线程标识，通常由平台、会话和用户拼装而成。
    thread_id: str = ""
    # 当前轮已经构建好的上下文总包。
    context_bundle: ContextBundle | None = None
    # 当前轮真正送进模型的消息序列，以及模型/工具回写后的消息累计。
    messages: tuple[BaseMessage, ...] = ()
    # 规范化后的查询文本，供 rewrite 和后续模型调用统一使用。
    canonical_query: str = ""
    # rewrite 阶段生成的补充说明，后续会插入系统消息中。
    rewrite_notes: tuple[str, ...] = ()
    # selector 阶段选中的工具大类集合。
    selected_tool_categories: tuple[ToolCategoryName, ...] = ()
    # selector 阶段根据分类推导出的工具名称集合。
    selected_tool_names: tuple[str, ...] = ()
    # selector 对当前工具决策的置信度估计。
    selector_confidence: float | None = None
    # 标记本轮是否已经直接命中核心工具，需要立刻执行工具。
    selector_requires_tool_execution: bool = False
    # 当前 chat_model 节点真正会绑定给模型的工具规格集合。
    active_tool_specs: tuple[ToolSpec, ...] = ()
    # 当前绑定给模型的工具名称集合，主要用于日志与调试。
    active_tool_names: tuple[str, ...] = ()
    # 当前这一次 tool_executor 节点刚执行出的工具结果集合。
    latest_tool_results: tuple[ToolExecutionResult, ...] = ()
    # 当前整轮图执行到此为止累计得到的所有工具结果集合。
    tool_results: tuple[ToolExecutionResult, ...] = ()
    # 如果已经拿到最终自然语言回复，就写在这里并结束图。
    final_reply: str | None = None
    # 当前已经跑了多少轮工具回路。
    tool_round: int = 0
    # 允许的最大工具回路次数，用于避免无限循环。
    max_tool_rounds: int = 3
