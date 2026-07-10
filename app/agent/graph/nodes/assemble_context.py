from __future__ import annotations

from app.agent.context.models import ContextBundle, ContextEvidenceBlock, ContextSessionSnapshot
from app.agent.context.system_prompt import SYSTEM_PROMPT
from app.agent.graph.runtime import GraphRuntimeContext
from app.memory.models import MemoryRecord, RetrievedMemoryHit

from ..state import ReplyState


def assemble_context_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    excluded_message_ids = {record.message_id for record in state.recent_records}
    excluded_message_ids.add(state.message.message_id)
    similar_records = tuple(
        context.services.conversation_memory_service.expand_memory_hits(
            user_id=state.message.sender_id,
            im_type=state.message.im_type,
            chat_id=state.message.chat_id,
            hits=state.reranked_memory_hits,
            exclude_message_ids=excluded_message_ids,
        )
    )
    evidence_blocks = _deduplicate_evidence(_convert_memory_records_to_evidence(similar_records))
    return state.model_copy(
        update={
            "context_bundle": ContextBundle(
                system_prompt=SYSTEM_PROMPT,
                current_message=state.message,
                session_snapshot=ContextSessionSnapshot(
                    chat_id=state.session_info.chat_id,
                    chat_type=state.message.chat_type,
                    im_type=state.session_info.im_type,
                    first_reply_time=state.session_info.first_reply_time,
                    latest_reply_time=state.session_info.latest_reply_time,
                ),
                recent_records=state.recent_records,
                evidence_blocks=evidence_blocks,
            ),
        }
    )


def _convert_memory_records_to_evidence(records: tuple[MemoryRecord, ...]) -> list[ContextEvidenceBlock]:
    evidence_blocks: list[ContextEvidenceBlock] = []
    for record in records:
        text_value = record.content.get("text")
        content_text = text_value.strip() if isinstance(text_value, str) else ""
        if not content_text:
            continue
        evidence_blocks.append(
            ContextEvidenceBlock(
                message_id=record.message_id,
                message_type=record.message_type,
                message_time=record.message_time,
                content_text=content_text,
            )
        )
    return evidence_blocks


def _deduplicate_evidence(
    evidence_blocks: list[ContextEvidenceBlock] | tuple[ContextEvidenceBlock, ...],
) -> tuple[ContextEvidenceBlock, ...]:
    deduplicated: dict[str, ContextEvidenceBlock] = {}
    for block in evidence_blocks:
        deduplicated[block.message_id] = block
    return tuple(sorted(deduplicated.values(), key=lambda block: (block.message_time, block.message_id)))
