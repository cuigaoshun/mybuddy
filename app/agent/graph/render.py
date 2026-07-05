from __future__ import annotations

from pathlib import Path

from .builder import build_graph


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
    output_path: str | Path | None = None,
) -> bytes:
    """直接基于依赖构建业务图并导出 PNG。"""

    # 适合在调试脚本或本地工具里一把生成业务图，而不用先手动拿 compiled graph。
    compiled_graph = build_graph(
    )
    return render_graph_png(compiled_graph=compiled_graph, output_path=output_path)


if __name__ == "__main__":
    output_path = Path(".agent-graph.png")
    png_bytes = build_and_render_graph_png(
        output_path=output_path,
    )
    print(f"已生成 Agent 图 PNG：{output_path}（{len(png_bytes)} bytes）")
