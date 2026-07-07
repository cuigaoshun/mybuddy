from __future__ import annotations

from langchain_core.tools import BaseTool

from .history_tools.search_history import HistoryToolDefinition
from .models import RegisteredTool, ToolCategory, ToolCategoryName
from .web_search_tools.search_web import WebSearchToolDefinition
from app.memory.service import ConversationMemoryService
from app.services.web_search import ExaWebSearchService


class ToolRegistry:
    """统一注册、查询和分类管理当前上下文层可用工具。"""

    def __init__(
        self,
        conversation_memory_service: ConversationMemoryService,
        web_search_service: ExaWebSearchService,
    ) -> None:
        # 用工具名做键保存全部工具。
        self._tools: dict[str, RegisteredTool] = {}
        # 用工具大类名映射该类别下的工具名列表。
        self._category_names: dict[ToolCategoryName, tuple[str, ...]] = {}
        # 保存全部核心工具名。
        self._core_tool_names: tuple[str, ...] = ()
        # 注册网页搜索工具。
        self.register(WebSearchToolDefinition.build(web_search_service))
        # 注册历史查询工具。
        self.register(HistoryToolDefinition.build(conversation_memory_service))

    def register(self, registered_tool: RegisteredTool) -> None:
        """注册一个已经带完整元信息的工具条目。"""

        # 保存到名字索引里。
        self._tools[registered_tool.name] = registered_tool
        # 读取当前类别已注册的工具名列表。
        category_tool_names = list(self._category_names.get(registered_tool.category.name, ()))
        # 避免重复加入同名工具。
        if registered_tool.name not in category_tool_names:
            category_tool_names.append(registered_tool.name)
        # 把更新后的工具名列表写回类别索引。
        self._category_names[registered_tool.category.name] = tuple(category_tool_names)
        # 如果工具自身标记为核心工具，就把它加入核心工具索引。
        if registered_tool.is_core and registered_tool.name not in self._core_tool_names:
            self._core_tool_names = (*self._core_tool_names, registered_tool.name)

    def get(self, name: str) -> BaseTool:
        """按工具名返回工具对象。"""

        return self._tools[name].tool

    def list(self) -> list[BaseTool]:
        """返回全部已注册工具对象。"""

        return [registered_tool.tool for registered_tool in self._tools.values()]

    def get_tools(self, names: list[str] | tuple[str, ...]) -> list[BaseTool]:
        """按工具名集合批量返回工具对象。"""

        return [self._tools[name].tool for name in names if name in self._tools]

    def list_core_tools(self) -> list[BaseTool]:
        """返回全部核心工具对象。"""

        return self.get_tools(self._core_tool_names)

    def list_core_tool_names(self) -> tuple[str, ...]:
        """返回全部核心工具名。"""

        return self._core_tool_names

    def list_non_core_categories(self) -> tuple[ToolCategory, ...]:
        """返回所有非核心工具所属的大类信息。"""

        # 用类别名做键去重。
        categories: dict[str, ToolCategory] = {}
        # 逐个遍历已注册工具。
        for registered_tool in self._tools.values():
            # 核心工具不参与非核心大类列表。
            if registered_tool.name in self._core_tool_names:
                continue
            # 记录当前非核心工具所属类别。
            categories[registered_tool.category.name] = registered_tool.category
        # 返回去重后的大类集合。
        return tuple(categories.values())

    def list_tool_categories(self) -> tuple[ToolCategory, ...]:
        """返回全部工具大类信息。"""

        categories: dict[str, ToolCategory] = {}
        for registered_tool in self._tools.values():
            categories[registered_tool.category.name] = registered_tool.category
        return tuple(categories.values())

    def list_registered_tools(self) -> tuple[RegisteredTool, ...]:
        """返回全部已注册工具条目。"""

        return tuple(self._tools.values())

    def list_category_tool_names(self, category_name: ToolCategoryName) -> tuple[str, ...]:
        """返回某个工具大类下的工具名集合。"""

        return self._category_names.get(category_name, ())

    def list_category_tools(self, category_name: ToolCategoryName) -> list[BaseTool]:
        """返回某个工具大类下的工具对象集合。"""

        return self.get_tools(self.list_category_tool_names(category_name))

    def get_category(self, category_name: ToolCategoryName) -> ToolCategory | None:
        """按大类名返回工具大类信息。"""

        for registered_tool in self._tools.values():
            if registered_tool.category.name == category_name:
                return registered_tool.category
        return None

    def read_tool_prompt_hint(self, name: str) -> str:
        """读取某个工具的 prompt_hint。"""

        return self._tools[name].prompt_hint
