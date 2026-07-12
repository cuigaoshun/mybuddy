from __future__ import annotations

from dataclasses import dataclass

from app.agent.context.tool import ContextTool
from app.agent.context.tools.registry import ToolRegistry
from app.memory.service import ConversationMemoryService
from app.memory.user_memory_service import UserMemoryService
from app.services.llm import ChatModel
from app.services.web_search import ExaWebSearchService


@dataclass(frozen=True)
class LLMProvider:
    """统一提供图内使用的基础模型。"""

    # 保存当前图流程共享使用的基础聊天模型。
    base_model: ChatModel

    def model(self) -> ChatModel:
        # 返回图内节点统一复用的模型实例。
        return self.base_model


@dataclass(frozen=True)
class GraphRuntimeContext:
    """LangGraph 节点共享的运行时依赖。"""

    # 提供图内统一使用的基础模型访问入口。
    llm_provider: LLMProvider
    # 把图所需的业务服务整体打包进来，供各节点按需读取具体服务。
    services: GraphServices
    # 聚合上下文格式化与预算控制能力，避免 runtime 顶层字段继续膨胀。
    context_tool: ContextTool
    # 统一提供核心工具与动态工具类别查询能力。
    tool_registry: ToolRegistry


@dataclass(frozen=True)
class GraphServices:
    """图装配阶段需要的业务服务聚合。"""

    # 负责最近消息读取、记忆召回与记忆窗口展开。
    conversation_memory_service: ConversationMemoryService
    # 负责读取用户级长期记忆快照。
    user_memory_service: UserMemoryService
    # 负责公开网页搜索能力，供工具节点或工具定义使用。
    web_search_service: ExaWebSearchService
