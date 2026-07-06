from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agent.context.tools.history import build_history_tool_definition
from app.agent.context.tools.web_search import build_web_search_tool_definition
from app.agent.context.tools.models import ToolCategory, ToolCategoryName, ToolDefinition, ToolSpec
from app.memory.service import ConversationMemoryService
from app.services.web_search import ExaWebSearchService


class ToolRegistry:
    def __init__(
        self,
        conversation_memory_service: ConversationMemoryService,
        web_search_service: ExaWebSearchService,
    ) -> None:
        history_definition = build_history_tool_definition(conversation_memory_service)
        web_search_definition = build_web_search_tool_definition(web_search_service)
        self._tool_definitions: dict[str, ToolDefinition] = {
            history_definition.spec.name: history_definition,
            web_search_definition.spec.name: web_search_definition,
        }

    def list_core_tool_specs(self) -> tuple[ToolSpec, ...]:
        return tuple(
            definition.spec
            for definition in self._tool_definitions.values()
            if definition.spec.category.name == "web_search_tools"
        )

    def list_core_langchain_tools(self) -> list[BaseTool]:
        return [tool_spec.tool for tool_spec in self.list_core_tool_specs()]

    def list_non_core_categories(self) -> tuple[ToolCategory, ...]:
        categories: dict[str, ToolCategory] = {}
        for definition in self._tool_definitions.values():
            if definition.spec.category.name == "web_search_tools":
                continue
            categories[definition.spec.category.name] = definition.spec.category
        return tuple(categories.values())

    def list_tool_categories(self) -> tuple[ToolCategory, ...]:
        categories: dict[str, ToolCategory] = {}
        for definition in self._tool_definitions.values():
            categories[definition.spec.category.name] = definition.spec.category
        return tuple(categories.values())

    def list_tool_specs(self) -> tuple[ToolSpec, ...]:
        return tuple(definition.spec for definition in self._tool_definitions.values())

    def list_langchain_tools(self) -> list[BaseTool]:
        return [definition.spec.tool for definition in self._tool_definitions.values()]

    def list_tool_specs_by_category(self, category_name: ToolCategoryName) -> tuple[ToolSpec, ...]:
        return tuple(
            definition.spec
            for definition in self._tool_definitions.values()
            if definition.spec.category.name == category_name
        )

    def list_langchain_tools_by_category(self, category_name: ToolCategoryName) -> list[BaseTool]:
        return [
            definition.spec.tool
            for definition in self._tool_definitions.values()
            if definition.spec.category.name == category_name
        ]

    def get_category(self, category_name: ToolCategoryName) -> ToolCategory | None:
        for definition in self._tool_definitions.values():
            if definition.spec.category.name == category_name:
                return definition.spec.category
        return None

    def get_definition(self, tool_name: str) -> ToolDefinition | None:
        return self._tool_definitions.get(tool_name)
