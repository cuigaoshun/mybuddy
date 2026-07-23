from __future__ import annotations

from dataclasses import dataclass

from app.agent.graph.main_graph.runtime import LLMProvider


@dataclass(frozen=True)
class ReminderGraphServices:
    """提醒图共享依赖占位。"""

    llm_provider: LLMProvider


@dataclass(frozen=True)
class ReminderGraphRuntimeContext:
    """提醒图节点共享运行时上下文。"""

    services: ReminderGraphServices
