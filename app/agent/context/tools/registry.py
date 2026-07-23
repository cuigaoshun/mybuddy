from __future__ import annotations

from langchain_core.tools import BaseTool

from .models import RegisteredTool, ToolCategory, ToolCategoryName, ToolCategorySelection


class ToolRegistry:
    """统一注册、查询和分类管理当前上下文层可用工具。"""

    def __init__(
        self,
        registered_tools: tuple[RegisteredTool, ...],
    ) -> None:
        # 用工具名做键保存全部工具。
        self._tools: dict[str, RegisteredTool] = {}
        # 用工具大类名映射该类别下的工具名列表。
        self._category_names: dict[ToolCategoryName, tuple[str, ...]] = {}
        # 保存全部核心工具名。
        self._core_tool_names: tuple[str, ...] = ()
        # 把外部已经构建好的工具条目统一注册进来。
        for registered_tool in registered_tools:
            self.register(registered_tool)

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

        categories: dict[str, list[RegisteredTool]] = {}
        # 逐个遍历已注册工具。
        for registered_tool in self._tools.values():
            # 核心工具不参与非核心大类列表。
            if registered_tool.name in self._core_tool_names:
                continue
            categories.setdefault(registered_tool.category.name, []).append(registered_tool)
        # 返回去重后的大类集合。
        return tuple(
            _build_category_with_tool_summaries(registered_tools)
            for registered_tools in categories.values()
        )

    def list_category_tool_names(self, category_name: ToolCategoryName) -> tuple[str, ...]:
        """返回某个工具大类下的工具名集合。"""

        return self._category_names.get(category_name, ())

    def list_categories_tool_names(self, category_names: ToolCategorySelection) -> tuple[str, ...]:
        """返回多个工具大类合并后的工具名集合。"""

        merged_names: list[str] = []
        for category_name in category_names:
            for tool_name in self.list_category_tool_names(category_name):
                if tool_name not in merged_names:
                    merged_names.append(tool_name)
        return tuple(merged_names)

    def list_categories_tools(self, category_names: ToolCategorySelection) -> list[BaseTool]:
        """返回多个工具大类合并后的工具对象集合。"""

        return self.get_tools(self.list_categories_tool_names(category_names))


def _build_category_with_tool_summaries(registered_tools: list[RegisteredTool]) -> ToolCategory:
    base_category = registered_tools[0].category
    tool_lines = [
        f"{index}. {registered_tool.name}：{registered_tool.description}"
        for index, registered_tool in enumerate(registered_tools, start=1)
    ]
    return ToolCategory(
        name=base_category.name,
        title=base_category.title,
        description=base_category.description + " 可用子工具包括：" + "；".join(tool_lines),
    )
