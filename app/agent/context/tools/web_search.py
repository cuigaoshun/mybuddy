from __future__ import annotations

from langchain_core.tools import tool

from app.memory.models import HistorySearchResult
from app.services.web_search import ExaWebSearchService, WebSearchResult

from .models import ToolCallContext, ToolCategory, ToolDefinition, ToolExecutionResult, ToolSpec, WebSearchToolInput

EMPTY_HISTORY_RESULTS: tuple[HistorySearchResult, ...] = ()

WEB_SEARCH_TOOLS_CATEGORY = ToolCategory(
    name="web_search_tools",
    title="网页搜索类",
    description="用于查询当前对话之外的公开网页信息，适合处理需要最新外部资料的问题。",
)


def build_web_search_tool_definition(web_search_service: ExaWebSearchService) -> ToolDefinition:
    @tool("search_web", args_schema=WebSearchToolInput)
    def search_web_tool(query: str, limit: int | None = None) -> str:
        """检索公开网页信息，返回与当前问题最相关的搜索结果摘要。"""
        del query, limit
        return "请通过图内工具执行器调用该工具。"

    spec = ToolSpec(
        category=WEB_SEARCH_TOOLS_CATEGORY,
        name="search_web",
        description="按查询语句检索公开网页内容，适合补充当前会话外的最新信息。",
        prompt_hint="当你需要当前会话与历史记忆之外的公开网页信息时，使用这个小工具。",
        tool=search_web_tool,
    )

    def execute(tool_args: dict[str, object], _: ToolCallContext, tool_call_id: str) -> ToolExecutionResult:
        query = tool_args.get("query")
        limit = tool_args.get("limit")
        search_results = web_search_service.search(
            query=query if isinstance(query, str) else "",
            limit=limit if isinstance(limit, int) else None,
        )
        return ToolExecutionResult(
            tool_name=spec.name,
            tool_call_id=tool_call_id,
            text=_format_web_search_results(search_results, web_search_service.is_available()),
            structured_results=EMPTY_HISTORY_RESULTS,
        )

    return ToolDefinition(spec=spec, execute=execute)


def _format_web_search_results(results: tuple[WebSearchResult, ...], is_available: bool) -> str:
    if not is_available:
        return "当前未配置 Exa API Key，暂时无法执行网页搜索。"
    if not results:
        return "未找到相关网页结果。"

    lines = ["以下是命中的网页搜索结果："]
    for index, result in enumerate(results, start=1):
        rank_text = str(result.rank) if result.rank is not None else str(index)
        detail_parts = [f"标题：{result.title}"]
        if result.domain:
            detail_parts.append(f"站点：{result.domain}")
        if result.url:
            detail_parts.append(f"链接：{result.url}")
        if result.snippet:
            detail_parts.append(f"摘要：{result.snippet}")
        lines.append(f"{rank_text}. " + "｜".join(detail_parts))
    return "\n".join(lines)
