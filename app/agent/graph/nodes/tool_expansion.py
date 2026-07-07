from __future__ import annotations

from app.agent.context.tools.models import ToolSpec
from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def tool_expansion_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    # 每一轮都会先把核心工具放进候选列表，保证主模型始终可直接使用它们。
    active_tool_specs = list(context.tool_registry.list_core_tool_specs())
    # 再把 selector 选中的工具大类下的工具逐个展开进候选列表。
    for category_name in state.selected_tool_categories:
        active_tool_specs.extend(context.tool_registry.list_tool_specs_by_category(category_name))

    # 用工具名做键去重，避免核心工具与分类工具重复出现。
    deduplicated_tool_specs: dict[str, ToolSpec] = {}
    for tool_spec in active_tool_specs:
        deduplicated_tool_specs[tool_spec.name] = tool_spec
    # 还原成去重后的稳定元组结构。
    resolved_tool_specs = tuple(deduplicated_tool_specs.values())
    # 同步提取工具名集合，主要用于日志与模型调用记录。
    active_tool_names = tuple(tool_spec.name for tool_spec in resolved_tool_specs)
    # 把本轮真正可用的工具集合写回图状态。
    return state.model_copy(
        update={
            "active_tool_specs": resolved_tool_specs,
            "active_tool_names": active_tool_names,
        }
    )
