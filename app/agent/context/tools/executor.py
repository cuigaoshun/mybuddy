from __future__ import annotations

from app.agent.context.tools.models import ToolCallContext, ToolExecutionResult, extract_tool_arguments
from app.agent.context.tools.registry import ToolRegistry


class ToolExecutor:
    """按工具名定位定义，并执行具体工具逻辑。"""

    def __init__(self, registry: ToolRegistry) -> None:
        # 保存工具注册中心，供执行时查找具体工具定义。
        self._registry = registry

    def execute(self, tool_name: str, tool_args: object, call_context: ToolCallContext, tool_call_id: str) -> ToolExecutionResult | None:
        # 先根据工具名找到对应定义，再交给具体小工具执行。
        definition = self._registry.get_definition(tool_name)
        # 未注册的工具直接返回空，交给上游决定如何兜底。
        if definition is None:
            return None
        # 先把模型传来的参数归一成普通字典。
        normalized_args = extract_tool_arguments(tool_args)
        # 调用具体工具定义的 execute 方法。
        return definition.execute(normalized_args, call_context, tool_call_id)
