from __future__ import annotations

from langchain_core.messages import BaseMessage

from app.agent.graph.memory_graph.runtime import MemoryGraphRuntimeContext
from app.agent.graph.memory_graph.state import MemoryExtractionResponse, MemoryMergeResponse


def parse_memory_extraction_response(
    context: MemoryGraphRuntimeContext,
    messages: tuple[BaseMessage, ...],
) -> MemoryExtractionResponse | None:
    """调用模型并解析长期记忆候选提取结果。"""

    structured_llm = context.llm_provider.model().with_structured_output(
        MemoryExtractionResponse,
        method="json_schema",
    )
    response = structured_llm.invoke(list(messages))
    if not isinstance(response, MemoryExtractionResponse):
        return None
    return response


def parse_memory_merge_response(
    context: MemoryGraphRuntimeContext,
    messages: tuple[BaseMessage, ...],
) -> MemoryMergeResponse | None:
    """调用模型并解析长期记忆合并结果。"""

    structured_llm = context.llm_provider.model().with_structured_output(
        MemoryMergeResponse,
        method="json_schema",
    )
    response = structured_llm.invoke(list(messages))
    if not isinstance(response, MemoryMergeResponse):
        return None
    return response
