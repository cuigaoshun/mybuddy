from __future__ import annotations

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agent.context.models import ContextBundle, ContextEvidenceBlock, ContextUserMemorySnapshot
from app.memory.models import ASSISTANT_MESSAGE_TYPE, USER_MESSAGE_TYPE, MemoryRecord, UserMemoryProfile


class ConversationContextFormatter:
    """把结构化上下文转换成适合模型消费的消息序列。"""

    def format(self, bundle: ContextBundle) -> tuple[BaseMessage, ...]:
        """把上下文包格式化成模型输入消息序列。"""

        # 系统提示词始终放在最前面。
        messages: list[BaseMessage] = [self._build_system_message(bundle)]
        user_memory_message = self._build_user_memory_message(bundle.user_memory_snapshot)
        if user_memory_message is not None:
            messages.append(user_memory_message)
        messages.append(self._build_runtime_context_message(bundle))
        # 历史证据单独组织成参考块。
        evidence_message = self._build_evidence_message(bundle.evidence_blocks)
        # 有历史证据时再拼进去。
        if evidence_message is not None:
            messages.append(evidence_message)
        messages.extend(self._build_recent_messages(bundle.recent_records))
        # 当前用户消息固定放在最后。
        messages.append(self._build_current_message(bundle))
        # 返回最终消息序列。
        return tuple(messages)

    def _build_system_message(self, bundle: ContextBundle) -> SystemMessage:
        """构建系统提示消息。"""

        return SystemMessage(content=bundle.system_prompt.strip())

    def _build_recent_messages(self, recent_records: tuple[MemoryRecord, ...]) -> list[BaseMessage]:
        """把最近消息记录转换成标准聊天消息列表。"""

        return [self._record_to_message(record) for record in recent_records]

    def _build_runtime_context_message(self, bundle: ContextBundle) -> SystemMessage:
        """构建运行时上下文消息。"""

        current_time_text = bundle.current_message.message_time.isoformat()
        return SystemMessage(
            content=(
                f"当前 IM 平台类型：{bundle.session_snapshot.im_type}\n"
                f"当前时间：{current_time_text}"
            )
        )

    def _build_user_memory_message(self, snapshot: ContextUserMemorySnapshot | None) -> SystemMessage | None:
        """把用户级长期记忆快照转换成系统参考消息。"""

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
        """把结构化用户画像格式化为模型可读 JSON。"""

        return json.dumps(user_profile.to_dict(), ensure_ascii=False, sort_keys=True)

    def _build_evidence_message(self, evidence_blocks: tuple[ContextEvidenceBlock, ...]) -> SystemMessage | None:
        """把历史证据块转换成系统参考消息。"""

        # 没有证据时不生成额外消息。
        if not evidence_blocks:
            return None
        # 先写参考标题。
        lines = ["以下是从历史记忆中召回的参考片段，仅供理解当前话题参考，不代表它们是刚刚连续发生的对话："]
        # 再按顺序展开证据详情。
        for index, block in enumerate(evidence_blocks, start=1):
            # 根据消息类型渲染角色名称。
            role_name = "用户" if block.message_type == USER_MESSAGE_TYPE else "助手"
            # 拼装单条证据文本。
            lines.append(f"{index}. 时间：{block.message_time.isoformat()}｜角色：{role_name}｜内容：{block.content_text}")
        # 返回历史证据系统消息。
        return SystemMessage(content="\n".join(lines))

    def _build_current_message(self, bundle: ContextBundle) -> HumanMessage:
        """构建当前用户问题消息。"""

        return HumanMessage(content=bundle.current_message.text)

    def _record_to_message(self, record: MemoryRecord) -> BaseMessage:
        """把记忆记录还原成模型更熟悉的消息对象。"""

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
