# 导出上下文构建器，供图构建与其他上层模块统一引用。
from app.agent.context.builder import ConversationContextBuilder
# 导出上下文消息预算裁剪器，供模型调用前控制 token 开销。
from app.agent.context.budget import ContextMessageBudgeter
# 导出上下文格式化器，负责把结构化上下文转成模型消息列表。
from app.agent.context.formatter import ConversationContextFormatter
# 导出上下文相关核心数据结构，方便外部模块直接类型引用。
from app.agent.context.models import ContextBundle, ContextEvidenceBlock, ContextSessionSnapshot

# 明确声明当前子包对外暴露的稳定接口。
__all__ = [
    # 导出上下文总包结构。
    "ContextBundle",
    # 导出历史证据块结构。
    "ContextEvidenceBlock",
    # 导出消息预算器。
    "ContextMessageBudgeter",
    # 导出会话快照结构。
    "ContextSessionSnapshot",
    # 导出上下文构建器。
    "ConversationContextBuilder",
    # 导出上下文格式化器。
    "ConversationContextFormatter",
]
