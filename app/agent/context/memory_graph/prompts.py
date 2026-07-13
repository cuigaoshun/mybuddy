from __future__ import annotations

import json
from typing import Final

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agent.graph.memory_graph.state import MemoryCandidate
from app.memory.models import ASSISTANT_MESSAGE_TYPE, USER_MESSAGE_TYPE, MemoryRecord, UserMemoryProfile

EXTRACT_MEMORY_SYSTEM_PROMPT: Final[str] = (
    "你负责从新增对话里提取适合写入长期记忆的候选信息。"
    "你只能输出 JSON，不要输出 Markdown、解释或额外文本。"
    "输出格式必须是 {\"candidates\": [{\"category\": str, \"content\": str, \"importance\": float}]}。"
    "只保留对长期陪伴有价值的信息，例如稳定事实、偏好、长期计划、关系变化。"
    "跳过寒暄、重复表达、短期事务噪声和无把握推断。"
    "category 当前固定使用 conversation_summary。"
    "importance 必须在 0 到 1 之间。"
)

MERGE_MEMORY_SYSTEM_PROMPT: Final[str] = (
    "你负责基于旧长期记忆和本轮新增候选记忆，生成新的长期记忆摘要，并输出用户画像的增量更新 patch。"
    "你只能输出 JSON，不要输出 Markdown、解释或额外文本。"
    "输出格式必须是 {\"long_term_memory_summary\": str | null, \"user_profile_patch\": {...}}。"
    "user_profile_patch 只能包含需要新增、修改或清空的字段。"
    "未变化字段不要回传。"
    "profile 只放稳定用户事实；preferences 只放用户偏好；relationship.affinity 只放用户与 Agent 的互动状态。"
    "如果需要删除字段，请显式返回 null。"
    "不要生成未定义的顶层字段，不要输出数组值，不要输出多层嵌套对象值，不要基于猜测补充隐私信息。"
)


def build_extract_memory_messages(conversation_records: tuple[MemoryRecord, ...]) -> tuple[BaseMessage, ...]:
    """构造长期记忆候选提取提示词。"""

    conversation_text = _format_conversation_records(conversation_records)
    return (
        SystemMessage(content=EXTRACT_MEMORY_SYSTEM_PROMPT),
        HumanMessage(content=f"请从以下新增对话中提取长期记忆候选：\n{conversation_text}"),
    )


def build_merge_memory_messages(
    existing_summary: str | None,
    existing_user_profile: UserMemoryProfile,
    important_candidates: tuple[MemoryCandidate, ...],
    conversation_records: tuple[MemoryRecord, ...],
) -> tuple[BaseMessage, ...]:
    """构造长期记忆合并提示词。"""

    summary_text = existing_summary.strip() if isinstance(existing_summary, str) and existing_summary.strip() else "<empty>"
    candidates_text = _format_memory_candidates(important_candidates)
    conversation_text = _format_conversation_records(conversation_records)
    user_profile_text = json.dumps(existing_user_profile.to_dict(), ensure_ascii=False, sort_keys=True)
    return (
        SystemMessage(content=MERGE_MEMORY_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"旧的长期记忆摘要：\n{summary_text}\n\n"
                f"旧的用户画像：\n{user_profile_text}\n\n"
                f"本轮重要候选记忆：\n{candidates_text}\n\n"
                f"本轮新增对话：\n{conversation_text}"
            )
        ),
    )


def _format_conversation_records(conversation_records: tuple[MemoryRecord, ...]) -> str:
    lines: list[str] = []
    for index, record in enumerate(conversation_records, start=1):
        text_value = record.content.get("text")
        content_text = text_value.strip() if isinstance(text_value, str) else ""
        if not content_text:
            continue
        role_name = _resolve_role_name(record.message_type)
        lines.append(
            f"{index}. 时间：{record.message_time.isoformat()}｜角色：{role_name}｜内容：{content_text}"
        )
    if not lines:
        return "<empty>"
    return "\n".join(lines)


def _format_memory_candidates(candidates: tuple[MemoryCandidate, ...]) -> str:
    lines: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        lines.append(
            f"{index}. 类别：{candidate.category}｜重要度：{candidate.importance:.2f}｜内容：{candidate.content}"
        )
    if not lines:
        return "<empty>"
    return "\n".join(lines)


def _resolve_role_name(message_type: int) -> str:
    if message_type == USER_MESSAGE_TYPE:
        return "用户"
    if message_type == ASSISTANT_MESSAGE_TYPE:
        return "助手"
    return "未知"
