from __future__ import annotations

from app.agent.context.tools.models import ToolSpec
from app.agent.graph.runtime import GraphRuntimeContext

from ..state import ReplyState


def tool_expansion_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    active_tool_specs = list(context.tool_registry.list_core_tool_specs())
    for category_name in state.selected_tool_categories:
        active_tool_specs.extend(context.tool_registry.list_tool_specs_by_category(category_name))

    deduplicated_tool_specs: dict[str, ToolSpec] = {}
    for tool_spec in active_tool_specs:
        deduplicated_tool_specs[tool_spec.name] = tool_spec
    resolved_tool_specs = tuple(deduplicated_tool_specs.values())
    active_tool_names = tuple(tool_spec.name for tool_spec in resolved_tool_specs)
    return state.model_copy(
        update={
            "active_tool_specs": resolved_tool_specs,
            "active_tool_names": active_tool_names,
        }
    )
