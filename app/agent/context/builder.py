from __future__ import annotations

from dataclasses import replace

from app.agent.context.models import ContextBundle, ContextEvidenceBlock, ContextSessionSnapshot
from app.agent.context.system_prompt import SYSTEM_PROMPT
from app.agent.context.tools.prompts import build_tool_category_prompt, build_tool_selector_prompt
from app.agent.context.tools.registry import ToolRegistry
from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo, HistorySearchResult, MemoryRecord
from app.memory.service import ConversationMemoryService


class ConversationContextBuilder:
    def __init__(self, conversation_memory_service: ConversationMemoryService) -> None:
        self._conversation_memory_service = conversation_memory_service
        self._tool_registry = ToolRegistry(conversation_memory_service)

    def build_initial_bundle(self, message: IncomingChatMessage, session_info: ChatSessionInfo) -> ContextBundle:
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
        # 把原始记忆记录转换成统一的历史证据块，便于后续统一格式化和裁剪。
        evidence_blocks = self._deduplicate_evidence(
            self._convert_memory_records_to_evidence(similar_records, source="similar_recall", recent_records=recent_records)
        )
        # 当前先接入稳定的大类配置，再由模型自行决定需要哪个大类和哪个小工具。
        enabled_tool_categories = self._tool_registry.list_tool_categories()
        enabled_tool_specs = self._tool_registry.list_tool_specs()
        return ContextBundle(
            system_prompt=SYSTEM_PROMPT,
            tool_selector_prompt=build_tool_selector_prompt(enabled_tool_categories),
            tool_category_prompt=build_tool_category_prompt(enabled_tool_categories, enabled_tool_specs),
            current_message=message,
            session_snapshot=self._build_session_snapshot(message, session_info),
            recent_records=recent_records,
            evidence_blocks=evidence_blocks,
            enabled_tool_categories=enabled_tool_categories,
            enabled_tool_specs=enabled_tool_specs,
        )

    def append_tool_results(self, bundle: ContextBundle, results: tuple[HistorySearchResult, ...]) -> ContextBundle:
        # 把工具查询补回来的历史结果也收敛成同一种证据结构。
        tool_evidence_blocks = self._deduplicate_evidence(
            [
                *bundle.tool_evidence_blocks,
                *self._convert_history_results_to_evidence(results),
            ]
        )
        return replace(bundle, tool_evidence_blocks=tool_evidence_blocks)

    def list_langchain_tools(self) -> list[object]:
        # 图层只拿到真正可绑定给模型的小工具对象，不关心注册细节。
        return self._tool_registry.list_langchain_tools()

    def get_tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    def _build_session_snapshot(
        self,
        message: IncomingChatMessage,
        session_info: ChatSessionInfo,
    ) -> ContextSessionSnapshot:
        # 这里只保留对模型有意义的会话信息，不暴露租约等运行态字段。
        return ContextSessionSnapshot(
            chat_id=session_info.chat_id,
            chat_type=message.chat_type,
            im_type=session_info.im_type,
            first_reply_time=session_info.first_reply_time,
            latest_reply_time=session_info.latest_reply_time,
        )

    def _convert_memory_records_to_evidence(
        self,
        records: tuple[MemoryRecord, ...],
        source: str,
        recent_records: tuple[MemoryRecord, ...],
    ) -> list[ContextEvidenceBlock]:
        # 用最近消息集合辅助判断哪些召回结果是窗口扩展出来的上下文片段。
        recent_message_ids = {record.message_id for record in recent_records}
        evidence_blocks: list[ContextEvidenceBlock] = []
        for record in records:
            text_value = record.content.get("text")
            content_text = text_value.strip() if isinstance(text_value, str) else ""
            if not content_text:
                continue
            # 相似召回默认按语义命中处理，后续统一交给 formatter 标注来源。
            evidence_blocks.append(
                ContextEvidenceBlock(
                    message_id=record.message_id,
                    message_type=record.message_type,
                    message_time=record.message_time,
                    content_text=content_text,
                    source=source,
                    matched_by_text=False,
                    matched_by_vector=True,
                    is_window_expanded=record.message_id not in recent_message_ids,
                )
            )
        return evidence_blocks

    def _convert_history_results_to_evidence(self, results: tuple[HistorySearchResult, ...]) -> list[ContextEvidenceBlock]:
        evidence_blocks: list[ContextEvidenceBlock] = []
        for result in results:
            text_value = result.record.content.get("text")
            content_text = text_value.strip() if isinstance(text_value, str) else ""
            if not content_text:
                continue
            # 历史查询工具已经带有命中方式信息，这里直接保留下来。
            evidence_blocks.append(
                ContextEvidenceBlock(
                    message_id=result.record.message_id,
                    message_type=result.record.message_type,
                    message_time=result.record.message_time,
                    content_text=content_text,
                    source="history_search",
                    matched_by_text=result.matched_by_text,
                    matched_by_vector=result.matched_by_vector,
                    is_window_expanded=False,
                )
            )
        return evidence_blocks

    def _deduplicate_evidence(self, evidence_blocks: list[ContextEvidenceBlock] | tuple[ContextEvidenceBlock, ...]) -> tuple[ContextEvidenceBlock, ...]:
        deduplicated: dict[str, ContextEvidenceBlock] = {}
        for block in evidence_blocks:
            existing = deduplicated.get(block.message_id)
            if existing is None:
                # 首次出现的消息直接保留。
                deduplicated[block.message_id] = block
                continue
            # 同一条消息被多路命中时，合并命中来源和窗口信息。
            deduplicated[block.message_id] = ContextEvidenceBlock(
                message_id=block.message_id,
                message_type=block.message_type,
                message_time=max(existing.message_time, block.message_time),
                content_text=existing.content_text or block.content_text,
                source=existing.source,
                matched_by_text=existing.matched_by_text or block.matched_by_text,
                matched_by_vector=existing.matched_by_vector or block.matched_by_vector,
                is_window_expanded=existing.is_window_expanded or block.is_window_expanded,
            )
        # 最终按时间顺序整理，方便 formatter 输出稳定的历史参考块。
        return tuple(
            sorted(
                deduplicated.values(),
                key=lambda block: (block.message_time, block.message_id),
            )
        )
