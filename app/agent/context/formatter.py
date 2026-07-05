from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agent.context.models import ContextBundle, ContextEvidenceBlock
from app.memory.models import ASSISTANT_MESSAGE_TYPE, USER_MESSAGE_TYPE, MemoryRecord


class ConversationContextFormatter:
    def format(self, bundle: ContextBundle) -> tuple[BaseMessage, ...]:
        # 系统提示词始终放在最前面，尽量保持前缀稳定以提升 KV cache 命中率。
        messages: list[BaseMessage] = [self._build_system_message(bundle)]
        # 最近连续对话继续使用标准聊天消息形式，让模型按自然对话理解。
        messages.extend(self._build_recent_messages(bundle.recent_records))
        # 相似召回得到的历史证据单独放成参考块，避免混入当前时间线。
        evidence_message = self._build_evidence_message(bundle.evidence_blocks)
        if evidence_message is not None:
            messages.append(evidence_message)
        # 工具补查得到的历史结果也独立标注，和预取证据分层展示。
        tool_evidence_message = self._build_tool_evidence_message(bundle.tool_evidence_blocks)
        if tool_evidence_message is not None:
            messages.append(tool_evidence_message)
        # 当前用户消息始终放在最后，保证最终提问位置稳定。
        messages.append(self._build_current_message(bundle))
        return tuple(messages)

    def _build_system_message(self, bundle: ContextBundle) -> SystemMessage:
        # 把固定系统提示和轻量会话摘要合并成稳定的系统前缀。
        lines = [bundle.system_prompt.strip()]
        if bundle.tool_selector_prompt:
            # 显式给模型一段“大类选择器”协议，先选 category 再选具体 tool。
            lines.append("")
            lines.append(bundle.tool_selector_prompt)
        if bundle.tool_category_prompt:
            # 工具说明按大类动态拼进系统层，兼顾稳定前缀和可扩展性。
            lines.append("")
            lines.append(bundle.tool_category_prompt)
        lines.append("当前会话信息：")
        lines.append(f"- 平台：{bundle.session_snapshot.im_type}")
        lines.append(f"- 会话类型：{bundle.session_snapshot.chat_type}")
        if bundle.session_snapshot.first_reply_time is not None:
            lines.append(f"- 首次回复时间：{bundle.session_snapshot.first_reply_time.isoformat()}")
        if bundle.session_snapshot.latest_reply_time is not None:
            lines.append(f"- 最近回复时间：{bundle.session_snapshot.latest_reply_time.isoformat()}")
        return SystemMessage(content="\n".join(lines))

    def _build_recent_messages(self, recent_records: tuple[MemoryRecord, ...]) -> list[BaseMessage]:
        return [self._record_to_message(record) for record in recent_records]

    def _build_evidence_message(self, evidence_blocks: tuple[ContextEvidenceBlock, ...]) -> SystemMessage | None:
        return self._build_reference_message(
            title="以下是从历史记忆中召回的参考片段，仅供理解当前话题参考，不代表它们是刚刚连续发生的对话：",
            evidence_blocks=evidence_blocks,
        )

    def _build_tool_evidence_message(self, tool_evidence_blocks: tuple[ContextEvidenceBlock, ...]) -> SystemMessage | None:
        return self._build_reference_message(
            title="以下是根据历史查询工具补充得到的参考片段，仅供回答当前问题参考：",
            evidence_blocks=tool_evidence_blocks,
        )

    def _build_reference_message(
        self,
        title: str,
        evidence_blocks: tuple[ContextEvidenceBlock, ...],
    ) -> SystemMessage | None:
        if not evidence_blocks:
            return None
        # 历史证据统一格式化成一段系统说明，明确它们只是参考材料。
        lines = [title]
        for index, block in enumerate(evidence_blocks, start=1):
            role_name = "用户" if block.message_type == USER_MESSAGE_TYPE else "助手"
            lines.append(
                f"{index}. 时间：{block.message_time.isoformat()}｜角色：{role_name}｜来源：{self._build_source_text(block)}｜内容：{block.content_text}"
            )
        return SystemMessage(content="\n".join(lines))

    def _build_current_message(self, bundle: ContextBundle) -> HumanMessage:
        return HumanMessage(content=bundle.current_message.text)

    def _record_to_message(self, record: MemoryRecord) -> BaseMessage:
        # 把记忆记录还原成模型最熟悉的人类/助手消息格式。
        text_value = record.content.get("text")
        content = text_value if isinstance(text_value, str) else ""
        if record.message_type == USER_MESSAGE_TYPE:
            return HumanMessage(content=content)
        if record.message_type == ASSISTANT_MESSAGE_TYPE:
            return AIMessage(content=content)
        return HumanMessage(content=content)

    def _build_source_text(self, block: ContextEvidenceBlock) -> str:
        # 给证据块补一个可读来源标签，帮助模型理解这是怎么命中的。
        source_name = "相似召回" if block.source == "similar_recall" else "历史查询"
        match_parts: list[str] = []
        if block.matched_by_text:
            match_parts.append("全文")
        if block.matched_by_vector:
            match_parts.append("语义")
        if block.is_window_expanded:
            match_parts.append("窗口")
        if not match_parts:
            return source_name
        return f"{source_name}（{' + '.join(match_parts)}）"
