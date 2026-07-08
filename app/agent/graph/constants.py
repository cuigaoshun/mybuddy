from __future__ import annotations

from enum import Enum


class GraphNodes(str, Enum):
    """统一管理当前 LangGraph 内部使用的节点名称。"""

    # 上下文加载节点，负责准备当前轮进入图前的上下文状态。
    LOAD_MEMORY = "load_memory"
    # 主模型节点，负责 selector 决策、常规推理与下一轮工具选择。
    CHAT_MODEL = "chat_model"
    # 核心工具执行节点，对应始终可直接调用的核心工具集合。
    CORE_TOOLS = "core_tools"
    # 动态工具执行节点，对应 selector 选中后开放的非核心工具集合。
    DYNAMIC_TOOLS = "dynamic_tools"
    # 图内路由层使用的结束标记，再由 builder 映射到 LangGraph 内置 END。
    END = "end"
