from __future__ import annotations

from pathlib import Path
import sys

# 兼容直接脚本运行场景，确保可以解析到仓库根目录下的 app 包。
if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from app.agent.graph.builder import build_graph
    from app.agent.graph.runtime import LLMProvider
    from app.memory.service import ConversationMemoryService
    from app.services.llm import ChatModel
    from app.services.web_search import ExaWebSearchService
else:
    from .builder import build_graph
    from .runtime import LLMProvider
    from app.memory.service import ConversationMemoryService
    from app.services.llm import ChatModel
    from app.services.web_search import ExaWebSearchService


def render_graph_png(compiled_graph, output_path: str | Path | None = None) -> bytes:
    """把已编译的 LangGraph 导出成 PNG，可选写入文件。"""

    # 通过 LangGraph 自带的 Mermaid 导图能力生成 PNG，可选写入本地文件。
    png_bytes = compiled_graph.get_graph().draw_mermaid_png()
    if output_path is not None:
        # 如果传了输出路径，就顺手落盘，方便本地调试或文档引用。
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(png_bytes)
    return png_bytes


def build_and_render_graph_png(
    llm_provider: LLMProvider,
    conversation_memory_service: ConversationMemoryService,
    web_search_service: ExaWebSearchService,
    output_path: str | Path | None = None,
) -> bytes:
    """直接基于依赖构建业务图并导出 PNG。"""

    # 适合在调试脚本或本地工具里一把生成业务图，而不用先手动拿 compiled graph。
    compiled_graph = build_graph(
        llm_provider=llm_provider,
        conversation_memory_service=conversation_memory_service,
        web_search_service=web_search_service,
    )
    return render_graph_png(compiled_graph=compiled_graph, output_path=output_path)


if __name__ == "__main__":
    # 只有本地脚本运行时才临时加载这些开发辅助依赖。
    from dependency_injector import providers
    from dotenv import load_dotenv

    from app.bootstrap.container import AppContainer
    from app.core.config import init_config
    from app.event.bus import EventBus

    # 先加载环境变量与配置。
    load_dotenv()
    config = init_config()

    # 构建容器并把配置对象覆盖进去。
    container = AppContainer()
    container.feishu_config.override(providers.Object(config.feishu))
    container.postgres_config.override(providers.Object(config.postgres))
    container.llm_config.override(providers.Object(config.llm))
    container.exa_config.override(providers.Object(config.exa))
    container.event_bus.override(providers.Object(EventBus()))

    # 指定默认输出路径。
    output_path = Path("./agent-graph.png")
    # 构建图并导出 PNG。
    png_bytes = build_and_render_graph_png(
        llm_provider=container.llm_provider(),
        conversation_memory_service=container.conversation_memory_service(),
        web_search_service=container.web_search_service(),
        output_path=output_path,
    )
    # 打印结果，方便本地确认输出是否成功。
    print(f"已生成 Agent 图 PNG：{output_path}（{len(png_bytes)} bytes）")
