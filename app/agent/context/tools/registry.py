from __future__ import annotations

from app.agent.context.tools.history import build_history_tool_definition
from app.agent.context.tools.models import ToolCategory, ToolDefinition, ToolSpec
from app.memory.service import ConversationMemoryService


class ToolRegistry:
    def __init__(self, conversation_memory_service: ConversationMemoryService) -> None:
        history_definition = build_history_tool_definition(conversation_memory_service)
        self._tool_definitions: dict[str, ToolDefinition] = {
            history_definition.spec.name: history_definition,
        }

    def list_tool_categories(self) -> tuple[ToolCategory, ...]:
        categories: dict[str, ToolCategory] = {}
        for definition in self._tool_definitions.values():
            categories[definition.spec.category.name] = definition.spec.category
        return tuple(categories.values())

    def list_tool_specs(self) -> tuple[ToolSpec, ...]:
        return tuple(definition.spec for definition in self._tool_definitions.values())

    def list_langchain_tools(self) -> list[object]:
        return [definition.spec.tool for definition in self._tool_definitions.values()]

    def get_definition(self, tool_name: str) -> ToolDefinition | None:
        return self._tool_definitions.get(tool_name)
