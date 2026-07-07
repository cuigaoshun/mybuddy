from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agent.context.tools.history import build_history_tool_definition
from app.agent.context.tools.web_search import build_web_search_tool_definition
from app.agent.context.tools.models import ToolCategory, ToolCategoryName, ToolDefinition, ToolSpec
from app.memory.service import ConversationMemoryService
from app.services.web_search import ExaWebSearchService


class ToolRegistry:
    """统一注册、查询和分类管理当前上下文层可用工具。"""

    def __init__(
        self,
        conversation_memory_service: ConversationMemoryService,
        web_search_service: ExaWebSearchService,
    ) -> None:
        # 先构建历史查询工具定义。
        history_definition = build_history_tool_definition(conversation_memory_service)
        # 再构建网页搜索工具定义。
        web_search_definition = build_web_search_tool_definition(web_search_service)
        # 用工具名做键，统一保存全部工具定义。
        self._tool_definitions: dict[str, ToolDefinition] = {
            history_definition.spec.name: history_definition,
            web_search_definition.spec.name: web_search_definition,
        }

    def list_core_tool_specs(self) -> tuple[ToolSpec, ...]:
        # 返回当前被视为核心工具的规格列表。
        return tuple(
            definition.spec
            for definition in self._tool_definitions.values()
            if definition.spec.category.name == "web_search_tools"
        )

    def list_core_langchain_tools(self) -> list[BaseTool]:
        # 把核心工具规格映射成真正的 LangChain 工具对象列表。
        return [tool_spec.tool for tool_spec in self.list_core_tool_specs()]

    def list_non_core_categories(self) -> tuple[ToolCategory, ...]:
        # 收集所有非核心工具大类，并按名称去重。
        categories: dict[str, ToolCategory] = {}
        for definition in self._tool_definitions.values():
            # 跳过当前被视为核心工具的类别。
            if definition.spec.category.name == "web_search_tools":
                continue
            # 记录非核心工具类别。
            categories[definition.spec.category.name] = definition.spec.category
        # 返回去重后的类别元组。
        return tuple(categories.values())

    def list_tool_categories(self) -> tuple[ToolCategory, ...]:
        # 收集全部工具大类，并按名称去重。
        categories: dict[str, ToolCategory] = {}
        for definition in self._tool_definitions.values():
            # 用类别名做键保留唯一类别对象。
            categories[definition.spec.category.name] = definition.spec.category
        # 返回全部工具大类。
        return tuple(categories.values())

    def list_tool_specs(self) -> tuple[ToolSpec, ...]:
        # 返回所有已注册工具的规格集合。
        return tuple(definition.spec for definition in self._tool_definitions.values())

    def list_langchain_tools(self) -> list[BaseTool]:
        # 返回所有已注册的 LangChain 工具对象。
        return [definition.spec.tool for definition in self._tool_definitions.values()]

    def list_tool_specs_by_category(self, category_name: ToolCategoryName) -> tuple[ToolSpec, ...]:
        # 按工具大类筛选工具规格。
        return tuple(
            definition.spec
            for definition in self._tool_definitions.values()
            if definition.spec.category.name == category_name
        )

    def list_langchain_tools_by_category(self, category_name: ToolCategoryName) -> list[BaseTool]:
        # 按工具大类筛选真正的 LangChain 工具对象。
        return [
            definition.spec.tool
            for definition in self._tool_definitions.values()
            if definition.spec.category.name == category_name
        ]

    def get_category(self, category_name: ToolCategoryName) -> ToolCategory | None:
        # 遍历已注册工具，查找目标类别对象。
        for definition in self._tool_definitions.values():
            if definition.spec.category.name == category_name:
                return definition.spec.category
        # 没找到目标类别时返回 None。
        return None

    def get_definition(self, tool_name: str) -> ToolDefinition | None:
        # 根据工具名返回对应工具定义。
        return self._tool_definitions.get(tool_name)
