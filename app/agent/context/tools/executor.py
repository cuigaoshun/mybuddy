from __future__ import annotations

from app.agent.context.tools.models import ToolCallContext, ToolExecutionResult, extract_tool_arguments
from app.agent.context.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(self, tool_name: str, tool_args: object, call_context: ToolCallContext, tool_call_id: str) -> ToolExecutionResult | None:
        # 先根据工具名找到对应定义，再交给具体小工具执行。
        definition = self._registry.get_definition(tool_name)
        if definition is None:
            return None
        normalized_args = extract_tool_arguments(tool_args)
        return definition.execute(normalized_args, call_context, tool_call_id)
