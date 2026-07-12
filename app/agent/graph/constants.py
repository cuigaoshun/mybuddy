from __future__ import annotations

from enum import Enum
from typing import Final

SELECT_TOOL_CATEGORY_TOOL_NAME: Final[str] = "select_tool_category"


class GraphNodes(str, Enum):
    """统一管理当前 LangGraph 内部使用的节点名称。"""

    LOAD_RECENT = "load_recent"
    RETRIEVE_MEMORY = "retrieve_memory"
    RERANK_MEMORY = "rerank_memory"
    ASSEMBLE_CONTEXT = "assemble_context"
    # 主模型节点，负责 selector 决策、常规推理与下一轮工具选择。
    CHAT_MODEL = "chat_model"
    # selector 结果消费节点：专门处理 select_tool_category，
    # 负责应用工具大类选择、剥离 selector 调用，并把真实工具调用继续留给执行节点。
    APPLY_TOOL_SELECTION = "apply_tool_selection"
    # 统一工具执行节点，对应当前轮允许执行的核心工具与动态工具集合。
    EXECUTE_TOOLS = "execute_tools"
    # 图内路由层使用的结束标记，再由 builder 映射到 LangGraph 内置 END。
    END = "end"


class ToolPhase(str, Enum):
    """统一表达当前工具选择流程所处阶段。"""

    # 当前轮仍在等待 selector 决策或重选工具大类。
    AWAIT_SELECTOR = "await_selector"
    # selector 已完成，下一跳需要先回 chat_model 基于新工具集再生成一轮。
    AWAIT_POST_SELECTOR_CHAT = "await_post_selector_chat"
    # 当前不处于 selector 决策轮，按常规回复/工具执行流程继续。
    IDLE = "idle"
