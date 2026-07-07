from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

# 统一约束工具大类名称，避免上下游各写一套字符串。
ToolCategoryName = Literal["history_tools", "memory_tools", "web_search_tools"]


@dataclass(frozen=True, slots=True)
class ToolCategory:
    """表示一个可供模型选择的工具大类。"""

    # 工具大类的内部稳定名称。
    name: ToolCategoryName
    # 工具大类给模型展示的中文标题。
    title: str
    # 工具大类的功能描述。
    description: str


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """表示注册到 registry 中的工具与其元信息。"""

    # 当前工具所属的大类信息。
    category: ToolCategory
    # 当前工具的唯一名称。
    name: str
    # 当前工具的用途描述。
    description: str
    # 当前工具的使用提示。
    prompt_hint: str
    # 当前工具是否属于核心工具。
    is_core: bool
    # 实际注册给模型和工具节点的工具对象。
    tool: BaseTool


class ToolDefinition(ABC):
    """约束具体工具定义类必须返回 RegisteredTool。"""

    @classmethod
    @abstractmethod
    def build(cls, *args, **kwargs) -> RegisteredTool:
        """基于外部依赖构建一个可注册的工具条目。"""


class SelectToolCategoryInput(BaseModel):
    """工具大类选择器的输入参数模型。"""

    # 当前选择的工具大类名称。
    category_name: ToolCategoryName = Field(description="选中的工具大类名称。")
