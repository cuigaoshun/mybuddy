from __future__ import annotations

from langchain_core.tools import tool

from app.memory.models import HistorySearchResult
from app.services.web_search import ExaWebSearchService, WebSearchResult

from .models import ToolCallContext, ToolCategory, ToolDefinition, ToolExecutionResult, ToolSpec, WebSearchToolInput

# 网页搜索工具不会返回历史结构化结果，因此这里固定为空元组。
EMPTY_HISTORY_RESULTS: tuple[HistorySearchResult, ...] = ()

# 定义网页搜索工具所属的大类元信息。
WEB_SEARCH_TOOLS_CATEGORY = ToolCategory(
    name="web_search_tools",
    title="网页搜索类",
    description="用于查询当前对话之外的公开网页信息，适合处理需要最新外部资料的问题。",
)


def build_web_search_tool_definition(web_search_service: ExaWebSearchService) -> ToolDefinition:
    # 定义一个仅供模型声明调用意图的 LangChain 工具壳。
    @tool("search_web", args_schema=WebSearchToolInput)
    def search_web_tool(query: str, limit: int | None = None) -> str:
        """检索公开网页信息，返回与当前问题最相关的搜索结果摘要。"""
        # 真实执行不在这里完成，避免模型直接短路调用业务逻辑。
        del query, limit
        return "请通过图内工具执行器调用该工具。"

    # 先组装工具规格，供注册中心和模型提示共同复用。
    spec = ToolSpec(
        category=WEB_SEARCH_TOOLS_CATEGORY,
        name="search_web",
        description="按查询语句检索公开网页内容，适合补充当前会话外的最新信息。",
        prompt_hint="当你需要当前会话与历史记忆之外的公开网页信息时，使用这个小工具。",
        tool=search_web_tool,
    )

    def execute(tool_args: dict[str, object], _: ToolCallContext, tool_call_id: str) -> ToolExecutionResult:
        # 从参数字典中读取查询语句。
        query = tool_args.get("query")
        # 从参数字典中读取可选返回条数。
        limit = tool_args.get("limit")
        # 调用网页搜索服务拿到结果集合。
        search_results = web_search_service.search(
            query=query if isinstance(query, str) else "",
            limit=limit if isinstance(limit, int) else None,
        )
        # 把网页搜索结果包装成统一工具执行结果。
        return ToolExecutionResult(
            tool_name=spec.name,
            tool_call_id=tool_call_id,
            text=_format_web_search_results(search_results, web_search_service.is_available()),
            structured_results=EMPTY_HISTORY_RESULTS,
        )

    # 返回最终的工具定义对象。
    return ToolDefinition(spec=spec, execute=execute)


def _format_web_search_results(results: tuple[WebSearchResult, ...], is_available: bool) -> str:
    # 没配置 Exa 时直接给出显式提示。
    if not is_available:
        return "当前未配置 Exa API Key，暂时无法执行网页搜索。"
    # 没查到结果时返回空结果文案。
    if not results:
        return "未找到相关网页结果。"

    # 先写标题行。
    lines = ["以下是命中的网页搜索结果："]
    # 再按顺序逐条展开搜索结果。
    for index, result in enumerate(results, start=1):
        # 优先使用搜索服务返回的 rank，否则回退到遍历序号。
        rank_text = str(result.rank) if result.rank is not None else str(index)
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
