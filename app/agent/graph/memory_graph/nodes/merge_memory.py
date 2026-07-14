from __future__ import annotations

"""长期记忆合并节点。

这个节点负责把旧长期记忆摘要、用户画像与本轮重要候选记忆汇总后交给模型，
得到新的摘要和用户画像 patch；如果模型结果不可用，则退回当前最保守的确定性拼接逻辑。
"""

from typing import Final

from app.agent.context.memory_graph import build_merge_memory_messages
from app.agent.graph.memory_graph.runtime import MemoryGraphRuntimeContext
from app.agent.graph.memory_graph.state import MemoryGraphState, MemoryMergeResponse, UserMemoryAffinityPatch, UserProfilePatch, build_empty_profile, build_now
from app.memory.models import UserMemory, UserMemoryAffinity, UserMemoryAttribute, UserMemoryAttributes, UserMemoryProfile, UserMemoryRelationship

MAX_SUMMARY_LINES: Final[int] = 20


def merge_memory_node(state: MemoryGraphState, context: MemoryGraphRuntimeContext) -> dict[str, object]:
    """合并长期记忆摘要与用户画像。"""

    existing_user_memory = state.existing_user_memory
    if not state.conversation_records:
        return {"merged_user_memory": existing_user_memory}
    merged_user_memory = _merge_user_memory_with_fallback(
        state=state,
        context=context,
        existing_user_memory=existing_user_memory,
    )
    return {"merged_user_memory": merged_user_memory}


def _merge_user_memory_with_fallback(
    state: MemoryGraphState,
    context: MemoryGraphRuntimeContext,
    existing_user_memory: UserMemory | None,
) -> UserMemory:
    """优先使用 LLM 合并长期记忆，失败时退回本地规则。"""

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
    """调用结构化输出模型，生成新摘要与用户画像 patch。"""

    existing_user_profile = existing_user_memory.user_profile if existing_user_memory is not None else build_empty_profile()
    structured_llm = context.llm_provider.model().with_structured_output(
        MemoryMergeResponse,
        method="json_schema",
    )
    response_model = structured_llm.invoke(
        list(
            build_merge_memory_messages(
                existing_summary=existing_user_memory.long_term_memory_summary if existing_user_memory is not None else None,
                existing_user_profile=existing_user_profile,
                important_candidates=state.important_candidates,
                conversation_records=state.conversation_records,
            )
        )
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
    """回退合并逻辑：摘要按行拼接，画像沿用旧值。"""

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
    """把摘要、画像和系统字段重新组装成最终长期记忆快照。"""

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
    """规范化摘要文本，去掉空行并限制最大行数。"""

    if summary is None:
        return None
    normalized_lines = [line.strip() for line in summary.splitlines() if line.strip()]
    if not normalized_lines:
        return None
    return "\n".join(normalized_lines[:MAX_SUMMARY_LINES])


def merge_user_profile_patch(
    existing_profile: UserMemoryProfile,
    patch: UserProfilePatch,
) -> UserMemoryProfile:
    """把模型返回的用户画像 patch 合并回完整用户画像。"""

    merged_profile_values = _merge_attribute_patch(
        base_values=existing_profile.profile.to_dict(),
        patch_values=patch.profile,
    )
    merged_preference_values = _merge_attribute_patch(
        base_values=existing_profile.preferences.to_dict(),
        patch_values=patch.preferences,
    )
    merged_affinity = _merge_affinity_patch(
        existing_affinity=existing_profile.relationship.affinity,
        affinity_patch=patch.relationship.affinity if patch.relationship is not None else None,
    )
    return UserMemoryProfile(
        profile=_build_user_memory_attributes(merged_profile_values),
        preferences=_build_user_memory_attributes(merged_preference_values),
        relationship=UserMemoryRelationship(affinity=merged_affinity),
    )


def _merge_attribute_patch(
    base_values: dict[str, str | bool | int | float],
    patch_values: dict[str, str | bool | int | float | None] | None,
) -> dict[str, str | bool | int | float]:
    """把一层扁平属性 patch 合并进旧属性字典。"""

    merged_values = dict(base_values)
    if patch_values is None:
        return merged_values
    for key, value in patch_values.items():
        normalized_key = key.strip()
        if not normalized_key:
            continue
        if value is None:
            merged_values.pop(normalized_key, None)
            continue
        merged_values[normalized_key] = value
    return merged_values


def _build_user_memory_attributes(
    values: dict[str, str | bool | int | float],
) -> UserMemoryAttributes:
    """把属性字典转换回稳定排序的 UserMemoryAttributes。"""

    items = tuple(
        UserMemoryAttribute(key=key, value=value)
        for key, value in sorted(values.items())
    )
    return UserMemoryAttributes(items=items)


def _merge_affinity_patch(
    existing_affinity: UserMemoryAffinity | None,
    affinity_patch: UserMemoryAffinityPatch | None,
) -> UserMemoryAffinity | None:
    """按字段粒度合并 relationship.affinity patch。"""

    if affinity_patch is None:
        return existing_affinity
    level = existing_affinity.level if existing_affinity is not None else None
    confidence = existing_affinity.confidence if existing_affinity is not None else None
    notes = existing_affinity.notes if existing_affinity is not None else None
    updated_at = existing_affinity.updated_at if existing_affinity is not None else None
    if affinity_patch.level is not None:
        level = affinity_patch.level
        updated_at = build_now()
    if affinity_patch.confidence is not None:
        confidence = affinity_patch.confidence
        updated_at = build_now()
    if affinity_patch.notes is not None:
        notes = affinity_patch.notes.strip() or None
        updated_at = build_now()
    if level is None and confidence is None and notes is None:
        return None
    return UserMemoryAffinity(
        level=level,
        confidence=confidence,
        updated_at=updated_at,
        notes=notes,
    )
