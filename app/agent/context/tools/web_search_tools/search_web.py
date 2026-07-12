from __future__ import annotations

from langchain_core.tools import tool

from app.agent.context.tools.models import RegisteredTool, ToolDefinition
from app.services.web_search import ExaWebSearchService, WebSearchResult

from .models import WEB_SEARCH_TOOLS_CATEGORY, WebSearchToolInput


class WebSearchToolDefinition(ToolDefinition):
    """统一封装网页搜索工具的构建逻辑。"""

    @classmethod
    def build(cls, web_search_service: ExaWebSearchService) -> RegisteredTool:
        """基于网页搜索服务构建网页搜索工具注册条目。"""

        @tool("search_web", args_schema=WebSearchToolInput)
        def search_web_tool(query: str, limit: int | None = None) -> str:
            """检索公开网页信息，返回与当前问题最相关的搜索结果摘要。"""

            # 调用网页搜索服务执行搜索。
            search_results = web_search_service.search(query=query, limit=limit)
            # 把搜索结果格式化成模型可阅读文本。
            return _format_web_search_results(search_results)

        # 直接返回带完整元信息的注册条目。
        return RegisteredTool(
            category=WEB_SEARCH_TOOLS_CATEGORY,
            name=search_web_tool.name,
            description="按查询语句检索公开网页内容，适合补充当前会话外的最新信息。",
            prompt_hint="当你需要当前会话与历史记忆之外的公开网页信息时，使用这个小工具。",
            is_core=False,
            tool=search_web_tool,
        )


def _format_web_search_results(results: tuple[WebSearchResult, ...]) -> str:
    """把网页搜索结果格式化成模型可阅读文本。"""

    # 没查到结果时返回空结果文案。
    if not results:
        return "未找到相关网页结果。"
    # 先写标题行。
    lines = ["以下是命中的网页搜索结果："]
    # 再按顺序逐条展开搜索结果。
    for index, result in enumerate(results, start=1):
        # 优先使用搜索服务返回的 rank，否则回退到遍历序号。
        rank_text = str(index)
        # 每条结果至少展示标题。
        detail_parts = [f"标题：{result.title}"]
        # 有域名时补上站点字段。
        if result.domain:
            detail_parts.append(f"站点：{result.domain}")
        # 有链接时补上链接字段。
        if result.url:
            detail_parts.append(f"链接：{result.url}")
        # 有摘要时补上摘要字段。
        if result.snippet:
            detail_parts.append(f"摘要：{result.snippet}")
        # 把这一条结果拼进最终输出列表。
        lines.append(f"{rank_text}. " + "｜".join(detail_parts))
    # 把全部结果拼成换行文本返回给模型。
    return "\n".join(lines)
