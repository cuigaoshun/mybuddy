from __future__ import annotations

"""提取长期记忆候选节点。

这个节点优先使用结构化输出能力让 LLM 直接返回候选记忆列表；
如果模型结果不可用，则回退到当前最保守的逐条文本提取逻辑。
"""

from app.agent.context.memory_graph import build_extract_memory_messages
from app.agent.graph.memory_graph.runtime import MemoryGraphRuntimeContext
from app.agent.graph.memory_graph.state import MemoryCandidate, MemoryExtractionResponse, MemoryGraphState


def extract_memory_node(state: MemoryGraphState, context: MemoryGraphRuntimeContext) -> dict[str, object]:
    """从新增对话中提取候选长期记忆。"""

    if not state.conversation_records:
        return {"extracted_candidates": ()}
    extracted_candidates = _extract_candidates_with_fallback(state=state, context=context)
    return {"extracted_candidates": extracted_candidates}


def _extract_candidates_with_fallback(
    state: MemoryGraphState,
    context: MemoryGraphRuntimeContext,
) -> tuple[MemoryCandidate, ...]:
    """优先走 LLM 语义提取，失败时回退到确定性提取。"""

    llm_candidates = _extract_candidates_with_llm(state=state, context=context)
    if llm_candidates is not None:
        return llm_candidates
    return _extract_candidates_deterministically(state)


def _extract_candidates_with_llm(
    state: MemoryGraphState,
    context: MemoryGraphRuntimeContext,
) -> tuple[MemoryCandidate, ...] | None:
    """调用结构化输出模型提取候选长期记忆。"""

    structured_llm = context.llm_provider.model().with_structured_output(
        MemoryExtractionResponse,
        method="json_schema",
    )
    response_model = structured_llm.invoke(list(build_extract_memory_messages(state.conversation_records)))
    if response_model is None:
        return None
    normalized_candidates = tuple(
        candidate
        for candidate in response_model.candidates
        if candidate.content.strip()
    )
    return normalized_candidates


def _extract_candidates_deterministically(state: MemoryGraphState) -> tuple[MemoryCandidate, ...]:
    """回退提取逻辑：把非空文本逐条包装成候选长期记忆。"""

    candidates: list[MemoryCandidate] = []
    for record in state.conversation_records:
        text_value = record.content.get("text")
        if not isinstance(text_value, str):
            continue
        normalized_text = text_value.strip()
        if not normalized_text:
            continue
        candidates.append(
            MemoryCandidate(
                category="conversation_summary",
                content=normalized_text,
                importance=1.0,
            )
        )
    return tuple(candidates)
