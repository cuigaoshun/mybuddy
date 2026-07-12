from __future__ import annotations

from app.agent.graph.memory_graph.runtime import MemoryGraphServices
from app.agent.graph.memory_graph.state import MemoryCandidate, MemoryGraphState, build_empty_profile, build_now
from app.memory.models import UserMemory


def load_conversation_node(state: MemoryGraphState, services: MemoryGraphServices) -> dict[str, object]:
    existing_user_memory = services.user_memory_service.get_user_memory(
        user_id=state.session.user_id,
        im_type=state.session.im_type,
    )
    after_message_id = existing_user_memory.last_processed_message_id if existing_user_memory is not None else None
    conversation_records = tuple(
        services.conversation_memory_service.list_messages_after_message_id(
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


def extract_memory_node(state: MemoryGraphState, services: MemoryGraphServices) -> dict[str, object]:
    del services
    if not state.conversation_records:
        return {"extracted_candidates": ()}
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
    return {"extracted_candidates": tuple(candidates)}


def score_importance_node(state: MemoryGraphState, services: MemoryGraphServices) -> dict[str, object]:
    del services
    important_candidates = tuple(candidate for candidate in state.extracted_candidates if candidate.importance >= 0.5)
    return {"important_candidates": important_candidates}


def merge_memory_node(state: MemoryGraphState, services: MemoryGraphServices) -> dict[str, object]:
    del services
    existing_user_memory = state.existing_user_memory
    if not state.conversation_records:
        return {"merged_user_memory": existing_user_memory}
    summary_parts: list[str] = []
    if existing_user_memory is not None and existing_user_memory.long_term_memory_summary:
        summary_parts.append(existing_user_memory.long_term_memory_summary.strip())
    for candidate in state.important_candidates:
        normalized_content = candidate.content.strip()
        if not normalized_content or normalized_content in summary_parts:
            continue
        summary_parts.append(normalized_content)
    merged_summary = "\n".join(summary_parts[:20]) or None
    last_processed_message_id = state.conversation_records[-1].message_id if state.conversation_records else (
        existing_user_memory.last_processed_message_id if existing_user_memory is not None else None
    )
    merged_user_memory = UserMemory(
        user_id=state.session.user_id,
        im_type=state.session.im_type,
        long_term_memory_summary=merged_summary,
        user_profile=existing_user_memory.user_profile if existing_user_memory is not None else build_empty_profile(),
        last_processed_message_id=last_processed_message_id,
        version=(existing_user_memory.version + 1) if existing_user_memory is not None else 1,
        created_at=existing_user_memory.created_at if existing_user_memory is not None else build_now(),
        updated_at=build_now(),
    )
    return {"merged_user_memory": merged_user_memory}


def save_memory_node(state: MemoryGraphState, services: MemoryGraphServices) -> dict[str, object]:
    if state.merged_user_memory is None or not state.conversation_records:
        return {"saved": False}
    services.user_memory_service.save_user_memory(state.merged_user_memory)
    return {"saved": True}
