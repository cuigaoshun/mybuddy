from __future__ import annotations

"""长期记忆图渲染脚本。

这个文件只用于把编译后的 storage graph 导出成图片，
便于观察当前节点结构，不参与线上业务执行。
"""

from pathlib import Path
import sys

# 直接脚本运行时补上仓库根目录，确保可以解析 app 包。
sys.path.append(str(Path(__file__).resolve().parents[3]))

from app.agent.graph.memory_graph.builder import build_memory_graph
from app.agent.graph.main_graph.runtime import LLMProvider
from app.agent.graph.memory_graph.runtime import MemoryGraphServices


def build_memory_graph_png(
    llm_provider: LLMProvider,
    services: MemoryGraphServices,
    output_path: str | Path | None = None,
) -> bytes:
    """基于依赖构建长期记忆处理图并导出 PNG，可选写入文件。"""

    compiled_graph = build_memory_graph(llm_provider=llm_provider, services=services)
    png_bytes = compiled_graph.get_graph().draw_mermaid_png()
    if output_path is not None:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(png_bytes)
    return png_bytes


if __name__ == "__main__":
    from dependency_injector import providers
    from dotenv import load_dotenv

    from app.bootstrap.container import AppContainer
    from app.core.config import init_config
    from app.event.bus import EventBus

    load_dotenv()
    config = init_config()

    container = AppContainer()
    container.feishu_config.override(providers.Object(config.feishu))
    container.postgres_config.override(providers.Object(config.postgres))
    container.llm_config.override(providers.Object(config.llm))
    container.web_search_config.override(providers.Object(config.web_search))
    container.event_bus.override(providers.Object(EventBus()))

    output_path = Path("./memory-graph.png")
    png_bytes = build_memory_graph_png(
        llm_provider=container.llm_provider(),
        services=container.memory_graph_services(),
        output_path=output_path,
    )
    print(f"已生成长期记忆图 PNG：{output_path}（{len(png_bytes)} bytes）")
