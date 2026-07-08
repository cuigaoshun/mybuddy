from __future__ import annotations

from enum import Enum


class GraphNodes(str, Enum):
    """统一管理当前 LangGraph 内部使用的节点名称。"""

    # 上下文加载节点，负责准备当前轮进入图前的上下文状态。
    LOAD_MEMORY = "load_memory"
    # 主模型节点，负责 selector 决策、常规推理与下一轮工具选择。
    CHAT_MODEL = "chat_model"
    # 统一工具执行节点，对应当前轮允许执行的核心工具与动态工具集合。
    EXECUTE_TOOLS = "execute_tools"
    # 图内路由层使用的结束标记，再由 builder 映射到 LangGraph 内置 END。
    END = "end"
