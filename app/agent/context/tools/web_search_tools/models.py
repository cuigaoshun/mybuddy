from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent.context.tools.models import ToolCategory

# 定义网页搜索工具所属的大类信息。
WEB_SEARCH_TOOLS_CATEGORY = ToolCategory(
    name="web_search_tools",
    title="网页搜索类",
    description="用于查询当前对话之外的公开网页信息，适合处理需要最新外部资料的问题。",
)


class WebSearchToolInput(BaseModel):
    """网页搜索工具的输入参数模型。"""

    # 要搜索的网页查询语句。
    query: str = Field(min_length=1, description="要检索的网页搜索查询语句。")
    # 返回结果条数，可为空时回退到系统默认值。
    limit: int | None = Field(default=None, ge=1, le=10, description="返回结果条数，默认使用系统配置。")
