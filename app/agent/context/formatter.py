from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agent.context.models import ContextBundle, ContextEvidenceBlock, ToolContextBlock
from app.memory.models import ASSISTANT_MESSAGE_TYPE, USER_MESSAGE_TYPE, MemoryRecord


class ConversationContextFormatter:
    """把结构化上下文转换成适合模型消费的消息序列。"""

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
        # 工具返回的普通参考文本也单独拼成系统说明块。
        tool_context_message = self._build_tool_context_message(bundle.tool_context_blocks)
        if tool_context_message is not None:
            messages.append(tool_context_message)
        # 当前用户消息始终放在最后，保证最终提问位置稳定。
        messages.append(self._build_current_message(bundle))
        return tuple(messages)

    def _build_system_message(self, bundle: ContextBundle) -> SystemMessage:
        # 把固定系统提示和轻量会话摘要合并成稳定的系统前缀。
        # 第一行先放系统提示词正文。
        lines = [bundle.system_prompt.strip()]
        # 再补一个固定标题，帮助模型区分下面是元信息。
        lines.append("当前会话信息：")
        # 写入平台类型。
        lines.append(f"- 平台：{bundle.session_snapshot.im_type}")
        # 写入会话类型。
        lines.append(f"- 会话类型：{bundle.session_snapshot.chat_type}")
        # 如果有首次回复时间，就一起告诉模型。
        if bundle.session_snapshot.first_reply_time is not None:
            lines.append(f"- 首次回复时间：{bundle.session_snapshot.first_reply_time.isoformat()}")
        # 如果有最近回复时间，也补充进去。
        if bundle.session_snapshot.latest_reply_time is not None:
            lines.append(f"- 最近回复时间：{bundle.session_snapshot.latest_reply_time.isoformat()}")
        # 返回最终系统消息对象。
        return SystemMessage(content="\n".join(lines))

    def _build_recent_messages(self, recent_records: tuple[MemoryRecord, ...]) -> list[BaseMessage]:
        # 把最近记忆逐条还原成标准聊天消息对象。
        return [self._record_to_message(record) for record in recent_records]

    def _build_evidence_message(self, evidence_blocks: tuple[ContextEvidenceBlock, ...]) -> SystemMessage | None:
        # 预取历史证据统一交给公共参考块构建函数处理。
        return self._build_reference_message(
            title="以下是从历史记忆中召回的参考片段，仅供理解当前话题参考，不代表它们是刚刚连续发生的对话：",
            evidence_blocks=evidence_blocks,
        )

    def _build_tool_evidence_message(self, tool_evidence_blocks: tuple[ContextEvidenceBlock, ...]) -> SystemMessage | None:
        # 工具补查回来的历史证据也走同一套参考块格式。
        return self._build_reference_message(
            title="以下是根据历史查询工具补充得到的参考片段，仅供回答当前问题参考：",
            evidence_blocks=tool_evidence_blocks,
        )

    def _build_reference_message(
        self,
        title: str,
        evidence_blocks: tuple[ContextEvidenceBlock, ...],
    ) -> SystemMessage | None:
        # 没有证据时不生成额外系统块。
        if not evidence_blocks:
            return None
        # 历史证据统一格式化成一段系统说明，明确它们只是参考材料。
        # 先写标题。
        lines = [title]
        # 再按顺序逐条展开证据详情。
        for index, block in enumerate(evidence_blocks, start=1):
            # 根据消息类型渲染成更自然的人类可读角色名。
            role_name = "用户" if block.message_type == USER_MESSAGE_TYPE else "助手"
            lines.append(
                f"{index}. 时间：{block.message_time.isoformat()}｜角色：{role_name}｜来源：{self._build_source_text(block)}｜内容：{block.content_text}"
            )
        # 把所有证据行拼成一个系统消息。
        return SystemMessage(content="\n".join(lines))

    def _build_current_message(self, bundle: ContextBundle) -> HumanMessage:
        # 当前消息固定作为最后一条人类消息输入模型。
        return HumanMessage(content=bundle.current_message.text)

    def _record_to_message(self, record: MemoryRecord) -> BaseMessage:
        # 把记忆记录还原成模型最熟悉的人类/助手消息格式。
        # 只读取一期约定的 text 字段。
        text_value = record.content.get("text")
        # 非字符串内容统一降级为空串。
        content = text_value if isinstance(text_value, str) else ""
        # 用户消息还原成人类消息。
        if record.message_type == USER_MESSAGE_TYPE:
            return HumanMessage(content=content)
        # 助手消息还原成 AI 消息。
        if record.message_type == ASSISTANT_MESSAGE_TYPE:
            return AIMessage(content=content)
        # 未知类型暂时按人类消息兜底。
        return HumanMessage(content=content)

    def _build_source_text(self, block: ContextEvidenceBlock) -> str:
        # 给证据块补一个可读来源标签，帮助模型理解这是怎么命中的。
        # 先根据来源类型决定主标签。
        source_name = "相似召回" if block.source == "similar_recall" else "历史查询"
        # 再收集更细的命中维度说明。
        match_parts: list[str] = []
        # 如果命中了全文检索，就补上全文标签。
        if block.matched_by_text:
            match_parts.append("全文")
        # 如果命中了语义检索，就补上语义标签。
        if block.matched_by_vector:
            match_parts.append("语义")
        # 如果这条消息来自窗口扩展，也显式标注。
        if block.is_window_expanded:
            match_parts.append("窗口")
        # 如果没有更细标签，直接返回来源名。
        if not match_parts:
            return source_name
        # 否则把来源名和细标签拼在一起。
        return f"{source_name}（{' + '.join(match_parts)}）"

    def _build_tool_context_message(self, tool_context_blocks: tuple[ToolContextBlock, ...]) -> SystemMessage | None:
        # 没有工具补充文本时不生成额外消息。
        if not tool_context_blocks:
            return None
        # 先写工具参考信息标题。
        lines = ["以下是本轮工具补充得到的参考信息，仅供回答当前问题参考："]
        # 再逐条列出工具名称和内容。
        for index, block in enumerate(tool_context_blocks, start=1):
            lines.append(f"{index}. 工具：{block.tool_name}｜内容：{block.content_text}")
        # 返回工具上下文消息。
        return SystemMessage(content="\n".join(lines))
