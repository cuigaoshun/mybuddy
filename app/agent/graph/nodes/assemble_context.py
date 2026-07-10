from __future__ import annotations

from app.agent.context.models import ContextBundle, ContextEvidenceBlock, ContextSessionSnapshot
from app.agent.context.system_prompt import SYSTEM_PROMPT
from app.agent.graph.runtime import GraphRuntimeContext
from app.memory.models import MemoryRecord, RetrievedMemoryHit

from ..state import ReplyState


def assemble_context_node(state: ReplyState, context: GraphRuntimeContext) -> dict[str, object]:
    """把最近对话与长期记忆证据组装成最终 ContextBundle。"""

    # 先记录最近对话里已经出现过的消息 ID，避免长期记忆窗口展开后与 recent 重复。
    excluded_message_ids = {record.message_id for record in state.recent_records}
    # 当前正在处理的这条用户消息也要排除，避免召回窗口把它重新塞回证据区。
    excluded_message_ids.add(state.message.message_id)
    # 根据重排后的长期记忆命中结果展开时间窗口，补齐更完整的上下文片段。
    similar_records = tuple(
        context.services.conversation_memory_service.expand_memory_hits(
            user_id=state.message.sender_id,
            im_type=state.message.im_type,
            chat_id=state.message.chat_id,
            hits=state.reranked_memory_hits,
            exclude_message_ids=excluded_message_ids,
        )
    )
    # 把展开后的原始消息记录转成统一证据块，并做去重整理。
    evidence_blocks = _deduplicate_evidence(_convert_memory_records_to_evidence(similar_records))
    return {
        # 在这里一次性组装最终 ContextBundle，后续 chat_model 只消费这一份结构化上下文。
        "context_bundle": ContextBundle(
            system_prompt=SYSTEM_PROMPT,
            current_message=state.message,
            # 会话快照用于补充模型对当前关系与会话状态的基本理解。
            session_snapshot=ContextSessionSnapshot(
                chat_id=state.session_info.chat_id,
                chat_type=state.message.chat_type,
                im_type=state.session_info.im_type,
                first_reply_time=state.session_info.first_reply_time,
                latest_reply_time=state.session_info.latest_reply_time,
            ),
            # 最近连续对话仍按标准聊天消息参与主上下文。
            recent_records=state.recent_records,
            # 长期记忆证据则作为参考片段单独组织。
            evidence_blocks=evidence_blocks,
        ),
    }


def _convert_memory_records_to_evidence(records: tuple[MemoryRecord, ...]) -> list[ContextEvidenceBlock]:
    """把窗口展开后的原始消息记录转换成统一证据块。"""

    # 初始化证据块列表。
    evidence_blocks: list[ContextEvidenceBlock] = []
    # 逐条把原始消息记录转换成可供 formatter 消费的证据结构。
    for record in records:
        # 只读取当前一期约定的 text 字段。
        text_value = record.content.get("text")
        # 非字符串内容统一降级为空串，避免把脏结构透传到模型。
        content_text = text_value.strip() if isinstance(text_value, str) else ""
        # 没有可读文本时直接跳过，避免生成空证据。
        if not content_text:
            continue
        # 当前消息记录转成统一证据块结构。
        evidence_blocks.append(
            ContextEvidenceBlock(
                message_id=record.message_id,
                message_type=record.message_type,
                message_time=record.message_time,
                content_text=content_text,
            )
        )
    # 返回全部可用证据块。
    return evidence_blocks


def _deduplicate_evidence(
    evidence_blocks: list[ContextEvidenceBlock] | tuple[ContextEvidenceBlock, ...],
) -> tuple[ContextEvidenceBlock, ...]:
    """按消息 ID 去重，并按时间顺序稳定输出证据块。"""

    # 用消息 ID 做键去重，后写入的同 ID 证据覆盖前面的重复项。
    deduplicated: dict[str, ContextEvidenceBlock] = {}
    # 逐条写入去重字典。
    for block in evidence_blocks:
        deduplicated[block.message_id] = block
    # 最终按消息时间和消息 ID 排序，保证输出顺序稳定可预期。
    return tuple(sorted(deduplicated.values(), key=lambda block: (block.message_time, block.message_id)))
