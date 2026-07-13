from __future__ import annotations

from typing import Final

from app.agent.context.memory_graph import build_extract_memory_messages, build_merge_memory_messages
from app.agent.graph.memory_graph.llm_io import parse_memory_extraction_response, parse_memory_merge_response
from app.agent.graph.memory_graph.profile_merge import merge_user_profile_patch
from app.agent.graph.memory_graph.runtime import MemoryGraphRuntimeContext
from app.agent.graph.memory_graph.state import MemoryCandidate, MemoryGraphState, build_empty_profile, build_now
from app.memory.models import UserMemory, UserMemoryProfile

MAX_SUMMARY_LINES: Final[int] = 20


def load_conversation_node(state: MemoryGraphState, context: MemoryGraphRuntimeContext) -> dict[str, object]:
    existing_user_memory = context.services.user_memory_service.get_user_memory(
        user_id=state.session.user_id,
        im_type=state.session.im_type,
    )
    after_message_id = existing_user_memory.last_processed_message_id if existing_user_memory is not None else None
    conversation_records = tuple(
        context.services.conversation_memory_service.list_messages_after_message_id(
            user_id=state.session.user_id,
            im_type=state.session.im_type,
            chat_id=state.session.chat_id,
            after_message_id=after_message_id,
            limit=50,
        )
    )
    return {
        "existing_user_memory": existing_user_memory,
        "conversation_records": conversation_records,
    }


def extract_memory_node(state: MemoryGraphState, context: MemoryGraphRuntimeContext) -> dict[str, object]:
    if not state.conversation_records:
        return {"extracted_candidates": ()}
    extracted_candidates = _extract_candidates_with_fallback(state=state, context=context)
    return {"extracted_candidates": extracted_candidates}


def score_importance_node(state: MemoryGraphState, context: MemoryGraphRuntimeContext) -> dict[str, object]:
    del context
    important_candidates = tuple(candidate for candidate in state.extracted_candidates if candidate.importance >= 0.5)
    return {"important_candidates": important_candidates}


def merge_memory_node(state: MemoryGraphState, context: MemoryGraphRuntimeContext) -> dict[str, object]:
    existing_user_memory = state.existing_user_memory
    if not state.conversation_records:
        return {"merged_user_memory": existing_user_memory}
    merged_user_memory = _merge_user_memory_with_fallback(
        state=state,
        context=context,
        existing_user_memory=existing_user_memory,
    )
    return {"merged_user_memory": merged_user_memory}


def save_memory_node(state: MemoryGraphState, context: MemoryGraphRuntimeContext) -> dict[str, object]:
    if state.merged_user_memory is None or not state.conversation_records:
        return {"saved": False}
    context.services.user_memory_service.save_user_memory(state.merged_user_memory)
    return {"saved": True}


def _extract_candidates_with_fallback(
    state: MemoryGraphState,
    context: MemoryGraphRuntimeContext,
) -> tuple[MemoryCandidate, ...]:
    llm_candidates = _extract_candidates_with_llm(state=state, context=context)
    if llm_candidates is not None:
        return llm_candidates
    return _extract_candidates_deterministically(state)


def _extract_candidates_with_llm(
    state: MemoryGraphState,
    context: MemoryGraphRuntimeContext,
) -> tuple[MemoryCandidate, ...] | None:
    response_model = parse_memory_extraction_response(
        context=context,
        messages=build_extract_memory_messages(state.conversation_records),
    )
    if response_model is None:
        return None
    normalized_candidates = tuple(
        candidate
        for candidate in response_model.candidates
        if candidate.content.strip()
    )
    return normalized_candidates


def _extract_candidates_deterministically(state: MemoryGraphState) -> tuple[MemoryCandidate, ...]:
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


def _merge_user_memory_with_fallback(
    state: MemoryGraphState,
    context: MemoryGraphRuntimeContext,
    existing_user_memory: UserMemory | None,
) -> UserMemory:
    llm_merged_user_memory = _merge_user_memory_with_llm(
        state=state,
        context=context,
        existing_user_memory=existing_user_memory,
    )
    if llm_merged_user_memory is not None:
        return llm_merged_user_memory
    return _merge_user_memory_deterministically(state, existing_user_memory)


def _merge_user_memory_with_llm(
    state: MemoryGraphState,
    context: MemoryGraphRuntimeContext,
    existing_user_memory: UserMemory | None,
) -> UserMemory | None:
    existing_user_profile = existing_user_memory.user_profile if existing_user_memory is not None else build_empty_profile()
    response_model = parse_memory_merge_response(
        context=context,
        messages=build_merge_memory_messages(
            existing_summary=existing_user_memory.long_term_memory_summary if existing_user_memory is not None else None,
            existing_user_profile=existing_user_profile,
            important_candidates=state.important_candidates,
            conversation_records=state.conversation_records,
        ),
    )
    if response_model is None:
        return None
    merged_summary = _normalize_summary(response_model.long_term_memory_summary)
    merged_profile = merge_user_profile_patch(
        existing_profile=existing_user_profile,
        patch=response_model.user_profile_patch,
    )
    return _build_user_memory(
        state=state,
        existing_user_memory=existing_user_memory,
        merged_summary=merged_summary,
        merged_profile=merged_profile,
    )


def _merge_user_memory_deterministically(
    state: MemoryGraphState,
    existing_user_memory: UserMemory | None,
) -> UserMemory:
    summary_parts: list[str] = []
    if existing_user_memory is not None and existing_user_memory.long_term_memory_summary:
        summary_parts.append(existing_user_memory.long_term_memory_summary.strip())
    for candidate in state.important_candidates:
        normalized_content = candidate.content.strip()
        if not normalized_content or normalized_content in summary_parts:
            continue
        summary_parts.append(normalized_content)
    merged_summary = "\n".join(summary_parts[:MAX_SUMMARY_LINES]) or None
    merged_profile = existing_user_memory.user_profile if existing_user_memory is not None else build_empty_profile()
    return _build_user_memory(
        state=state,
        existing_user_memory=existing_user_memory,
        merged_summary=merged_summary,
        merged_profile=merged_profile,
    )


def _build_user_memory(
    state: MemoryGraphState,
    existing_user_memory: UserMemory | None,
    merged_summary: str | None,
    merged_profile: UserMemoryProfile,
) -> UserMemory:
    last_processed_message_id = state.conversation_records[-1].message_id if state.conversation_records else (
        existing_user_memory.last_processed_message_id if existing_user_memory is not None else None
    )
    return UserMemory(
        user_id=state.session.user_id,
        im_type=state.session.im_type,
        long_term_memory_summary=merged_summary,
        user_profile=merged_profile,
        last_processed_message_id=last_processed_message_id,
        version=(existing_user_memory.version + 1) if existing_user_memory is not None else 1,
        created_at=existing_user_memory.created_at if existing_user_memory is not None else build_now(),
        updated_at=build_now(),
    )


def _normalize_summary(summary: str | None) -> str | None:
    if summary is None:
        return None
    normalized_lines = [line.strip() for line in summary.splitlines() if line.strip()]
    if not normalized_lines:
        return None
    return "\n".join(normalized_lines[:MAX_SUMMARY_LINES])
