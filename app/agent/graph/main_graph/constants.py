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
    CHAT_MODEL = "chat_model"
    EXECUTE_TOOLS = "execute_tools"
    END = "end"


class ToolPhase(str, Enum):
    """统一表达当前工具选择流程所处阶段。"""

    AWAIT_SELECTOR = "await_selector"
    AWAIT_POST_SELECTOR_CHAT = "await_post_selector_chat"
    IDLE = "idle"
