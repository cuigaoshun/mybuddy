from __future__ import annotations

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agent.context.main_graph.models import ContextBundle, ContextEvidenceBlock, ContextUserMemorySnapshot
from app.storage.models import ASSISTANT_MESSAGE_TYPE, USER_MESSAGE_TYPE, MemoryRecord, UserMemoryProfile


class ConversationContextFormatter:
    """把结构化上下文转换成适合模型消费的消息序列。"""

    def format(self, bundle: ContextBundle) -> tuple[BaseMessage, ...]:
        messages: list[BaseMessage] = [self._build_system_message(bundle)]
        user_memory_message = self._build_user_memory_message(bundle.user_memory_snapshot)
        if user_memory_message is not None:
            messages.append(user_memory_message)
        messages.append(self._build_runtime_context_message(bundle))
        evidence_message = self._build_evidence_message(bundle.evidence_blocks)
        if evidence_message is not None:
            messages.append(evidence_message)
        messages.extend(self._build_recent_messages(bundle.recent_records))
        messages.append(self._build_current_message(bundle))
        return tuple(messages)

    def _build_system_message(self, bundle: ContextBundle) -> SystemMessage:
        return SystemMessage(content=bundle.system_prompt.strip())

    def _build_recent_messages(self, recent_records: tuple[MemoryRecord, ...]) -> list[BaseMessage]:
        return [self._record_to_message(record) for record in recent_records]

    def _build_runtime_context_message(self, bundle: ContextBundle) -> SystemMessage:
        current_time_text = bundle.current_message.message_time.isoformat()
        return SystemMessage(
            content=(
                f"当前 IM 平台类型：{bundle.session_snapshot.im_type}\n"
                f"当前时间：{current_time_text}"
            )
        )

    def _build_user_memory_message(self, snapshot: ContextUserMemorySnapshot | None) -> SystemMessage | None:
        if snapshot is None:
            return None
        lines: list[str] = []
        if snapshot.long_term_memory_summary:
            lines.append(f"长期记忆摘要：{snapshot.long_term_memory_summary}")
        if snapshot.user_profile is not None:
            lines.append("用户长期属性：")
            lines.append(self._format_user_profile(snapshot.user_profile))
        if not lines:
            return None
        return SystemMessage(content="\n".join(lines))

    def _format_user_profile(self, user_profile: UserMemoryProfile) -> str:
        return json.dumps(user_profile.to_dict(), ensure_ascii=False, sort_keys=True)

    def _build_evidence_message(self, evidence_blocks: tuple[ContextEvidenceBlock, ...]) -> SystemMessage | None:
        if not evidence_blocks:
            return None
        lines = ["以下是从历史记忆中召回的参考片段，仅供理解当前话题参考，不代表它们是刚刚连续发生的对话："]
        for index, block in enumerate(evidence_blocks, start=1):
            role_name = "用户" if block.message_type == USER_MESSAGE_TYPE else "助手"
            lines.append(f"{index}. 时间：{block.message_time.isoformat()}｜角色：{role_name}｜内容：{block.content_text}")
        return SystemMessage(content="\n".join(lines))

    def _build_current_message(self, bundle: ContextBundle) -> HumanMessage:
        return HumanMessage(content=bundle.current_message.text)

    def _record_to_message(self, record: MemoryRecord) -> BaseMessage:
        text_value = record.content.get("text")
        content = text_value if isinstance(text_value, str) else ""
        if record.message_type == USER_MESSAGE_TYPE:
            return HumanMessage(content=content)
        if record.message_type == ASSISTANT_MESSAGE_TYPE:
            return AIMessage(content=content)
        return HumanMessage(content=content)
