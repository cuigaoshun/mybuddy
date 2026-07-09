from __future__ import annotations

from pathlib import Path
import sys

# 直接脚本运行时补上仓库根目录，确保可以解析 app 包。
sys.path.append(str(Path(__file__).resolve().parents[3]))

from app.agent.graph.builder import build_graph
from app.agent.graph.runtime import GraphServices, LLMProvider


def build_graph_png(
    llm_provider: LLMProvider,
    service: GraphServices,
    output_path: str | Path | None = None,
) -> bytes:
    """基于依赖构建业务图并导出 PNG，可选写入文件。"""

    # 直接构建业务图并生成 Mermaid PNG。
    compiled_graph = build_graph(
        llm_provider=llm_provider,
        service=service,
    )
    png_bytes = compiled_graph.get_graph().draw_mermaid_png()
    if output_path is not None:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(png_bytes)
    return png_bytes


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
    png_bytes = build_graph_png(
        llm_provider=container.llm_provider(),
        service=container.graph_services(),
        output_path=output_path,
    )
    # 打印结果，方便本地确认输出是否成功。
    print(f"已生成 Agent 图 PNG：{output_path}（{len(png_bytes)} bytes）")
