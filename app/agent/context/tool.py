from __future__ import annotations

from dataclasses import dataclass

from app.agent.context.budget import ContextMessageBudgeter
from app.agent.context.formatter import ConversationContextFormatter


@dataclass(frozen=True)
class ContextTool:
    """聚合上下文格式化与预算控制能力。"""

    # 负责把结构化上下文转换成模型消息序列。
    formatter: ConversationContextFormatter
    # 负责按模型上下文预算裁剪消息长度。
    budgeter: ContextMessageBudgeter
