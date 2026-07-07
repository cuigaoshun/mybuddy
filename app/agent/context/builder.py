from __future__ import annotations

from app.agent.context.models import ContextBundle, ContextEvidenceBlock, ContextSessionSnapshot
from app.agent.context.system_prompt import SYSTEM_PROMPT
from app.agent.context.tools.registry import ToolRegistry
from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo, MemoryRecord
from app.memory.service import ConversationMemoryService
from app.services.web_search import ExaWebSearchService


class ConversationContextBuilder:
    """负责构建回复所需的初始上下文，并暴露工具注册中心。"""

    def __init__(
        self,
        conversation_memory_service: ConversationMemoryService,
        web_search_service: ExaWebSearchService,
    ) -> None:
        # 保存对话记忆服务，后续用于读取最近消息和相似召回结果。
        self._conversation_memory_service = conversation_memory_service
        # 提前创建工具注册中心，统一收拢全部工具对象。
        self._tool_registry = ToolRegistry(conversation_memory_service, web_search_service)

    def build_initial_bundle(self, message: IncomingChatMessage, session_info: ChatSessionInfo) -> ContextBundle:
        """基于当前消息和会话信息构建初始上下文包。"""

        # 先读取最近连续对话，作为当前回复最核心的上下文。
        recent_records = tuple(
            self._conversation_memory_service.list_recent_messages(
                user_id=message.sender_id,
                im_type=message.im_type,
                chat_id=message.chat_id,
                exclude_message_id=message.message_id,
            )
        )
        # 把最近消息和当前消息排除掉，避免相似召回重复命中它们。
        excluded_message_ids = {record.message_id for record in recent_records}
        excluded_message_ids.add(message.message_id)
        # 再根据当前用户输入召回历史上相似的话题片段。
        similar_records = tuple(
            self._conversation_memory_service.search_similar_messages(
                user_id=message.sender_id,
                im_type=message.im_type,
                chat_id=message.chat_id,
                query_text=message.text,
                limit=3,
                exclude_message_ids=excluded_message_ids,
            )
        )
        # 把原始记忆记录转换成统一证据块，并做去重整理。
        evidence_blocks = self._deduplicate_evidence(self._convert_memory_records_to_evidence(similar_records))
        # 返回当前轮的完整上下文包。
        return ContextBundle(
            system_prompt=SYSTEM_PROMPT,
            current_message=message,
            session_snapshot=self._build_session_snapshot(message, session_info),
            recent_records=recent_records,
            evidence_blocks=evidence_blocks,
        )

    def get_tool_registry(self) -> ToolRegistry:
        """返回当前上下文层持有的工具注册中心。"""

        return self._tool_registry

    def _build_session_snapshot(
        self,
        message: IncomingChatMessage,
        session_info: ChatSessionInfo,
    ) -> ContextSessionSnapshot:
        """构建对模型有意义的会话摘要信息。"""

        return ContextSessionSnapshot(
            chat_id=session_info.chat_id,
            chat_type=message.chat_type,
            im_type=session_info.im_type,
            first_reply_time=session_info.first_reply_time,
            latest_reply_time=session_info.latest_reply_time,
        )

    def _convert_memory_records_to_evidence(self, records: tuple[MemoryRecord, ...]) -> list[ContextEvidenceBlock]:
        """把记忆记录转换成统一证据块。"""

        # 初始化证据块列表。
        evidence_blocks: list[ContextEvidenceBlock] = []
        # 逐条处理记忆记录。
        for record in records:
            # 只读取一期约定的文本字段。
            text_value = record.content.get("text")
            # 非字符串内容统一降级为空串。
            content_text = text_value.strip() if isinstance(text_value, str) else ""
            # 没有可读内容时直接跳过。
            if not content_text:
                continue
            # 把当前消息记录转换成证据块。
            evidence_blocks.append(
                ContextEvidenceBlock(
                    message_id=record.message_id,
                    message_type=record.message_type,
                    message_time=record.message_time,
                    content_text=content_text,
                )
            )
        # 返回转换后的证据块列表。
        return evidence_blocks

    def _deduplicate_evidence(self, evidence_blocks: list[ContextEvidenceBlock] | tuple[ContextEvidenceBlock, ...]) -> tuple[ContextEvidenceBlock, ...]:
        """按消息 ID 去重并按时间排序证据块。"""

        # 用消息 ID 做键，保留唯一证据块。
        deduplicated: dict[str, ContextEvidenceBlock] = {}
        # 逐条处理证据块。
        for block in evidence_blocks:
            deduplicated[block.message_id] = block
        # 最后按时间和消息 ID 排序，保证输出稳定。
        return tuple(sorted(deduplicated.values(), key=lambda block: (block.message_time, block.message_id)))
