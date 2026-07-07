from __future__ import annotations

from dataclasses import replace

from app.agent.context.models import ContextBundle, ContextEvidenceBlock, ContextEvidenceSource, ContextSessionSnapshot, ToolContextBlock
from app.agent.context.system_prompt import SYSTEM_PROMPT
from app.agent.context.tools.registry import ToolRegistry
from app.event.models import IncomingChatMessage
from app.memory.models import ChatSessionInfo, HistorySearchResult, MemoryRecord
from app.memory.service import ConversationMemoryService
from app.services.web_search import ExaWebSearchService


class ConversationContextBuilder:
    """负责构建回复所需的上下文总包，并在工具回合中持续补充。"""

    def __init__(
        self,
        conversation_memory_service: ConversationMemoryService,
        web_search_service: ExaWebSearchService,
    ) -> None:
        # 保存对话记忆服务，后续用于拉取最近消息与相似召回结果。
        self._conversation_memory_service = conversation_memory_service
        # 提前创建工具注册中心，统一收拢历史查询与网页搜索工具。
        self._tool_registry = ToolRegistry(conversation_memory_service, web_search_service)

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
        return ContextBundle(
            # 固定系统提示词作为上下文总包的一部分。
            system_prompt=SYSTEM_PROMPT,
            # 当前用户消息作为本轮主问题。
            current_message=message,
            # 构建会话快照，补充平台与回复时间等摘要信息。
            session_snapshot=self._build_session_snapshot(message, session_info),
            # 最近消息直接写入上下文。
            recent_records=recent_records,
            # 预取证据块也一并放入上下文。
            evidence_blocks=evidence_blocks,
        )

    def append_tool_results(self, bundle: ContextBundle, results: tuple[HistorySearchResult, ...]) -> ContextBundle:
        # 把工具查询补回来的历史结果也收敛成同一种证据结构。
        tool_evidence_blocks = self._deduplicate_evidence(
            [
                *bundle.tool_evidence_blocks,
                *self._convert_history_results_to_evidence(results),
            ]
        )
        # 返回追加了工具历史证据的新上下文包。
        return replace(bundle, tool_evidence_blocks=tool_evidence_blocks)

    def append_tool_context(self, bundle: ContextBundle, tool_name: str, content_text: str) -> ContextBundle:
        # 先裁掉工具结果两端空白，避免空内容污染上下文。
        normalized_content = content_text.strip()
        # 纯空字符串直接忽略。
        if normalized_content == "":
            return bundle
        # 通过不可变追加方式把工具文本上下文并入原 bundle。
        tool_context_blocks = tuple(
            [
                *bundle.tool_context_blocks,
                ToolContextBlock(tool_name=tool_name, content_text=normalized_content),
            ]
        )
        # 返回追加了工具文本上下文的新 bundle。
        return replace(bundle, tool_context_blocks=tool_context_blocks)

    def get_tool_registry(self) -> ToolRegistry:
        # 暴露注册中心，供图节点读取工具定义和分类信息。
        return self._tool_registry

    def _build_session_snapshot(
        self,
        message: IncomingChatMessage,
        session_info: ChatSessionInfo,
    ) -> ContextSessionSnapshot:
        # 这里只保留对模型有意义的会话信息，不暴露租约等运行态字段。
        return ContextSessionSnapshot(
            # 使用 session_info 里的 chat_id 作为会话唯一标识。
            chat_id=session_info.chat_id,
            # 使用消息上的 chat_type，帮助模型区分场景。
            chat_type=message.chat_type,
            # 使用会话记录上的平台类型。
            im_type=session_info.im_type,
            # 带上首次回复时间，帮助模型理解关系持续时长。
            first_reply_time=session_info.first_reply_time,
            # 带上最近回复时间，帮助模型理解最近互动时间。
            latest_reply_time=session_info.latest_reply_time,
        )

    def _convert_memory_records_to_evidence(
        self,
        records: tuple[MemoryRecord, ...],
        source: ContextEvidenceSource,
        recent_records: tuple[MemoryRecord, ...],
    ) -> list[ContextEvidenceBlock]:
        # 用最近消息集合辅助判断哪些召回结果是窗口扩展出来的上下文片段。
        # 先把最近消息 ID 提取出来，供后续判断是否窗口扩展。
        recent_message_ids = {record.message_id for record in recent_records}
        # 初始化证据块列表。
        evidence_blocks: list[ContextEvidenceBlock] = []
        # 遍历每一条召回结果并转成统一结构。
        for record in records:
            # 只读取一期约定的文本字段。
            text_value = record.content.get("text")
            # 非字符串内容统一归一成空串。
            content_text = text_value.strip() if isinstance(text_value, str) else ""
            # 没有可读内容的记录直接跳过。
            if not content_text:
                continue
            # 相似召回默认按语义命中处理，后续统一交给 formatter 标注来源。
            evidence_blocks.append(
                ContextEvidenceBlock(
                    # 写入消息 ID。
                    message_id=record.message_id,
                    # 写入消息类型。
                    message_type=record.message_type,
                    # 写入消息时间。
                    message_time=record.message_time,
                    # 写入文本内容。
                    content_text=content_text,
                    # 写入来源类型。
                    source=source,
                    # 相似召回阶段默认不标全文命中。
                    matched_by_text=False,
                    # 相似召回阶段默认标记为语义命中。
                    matched_by_vector=True,
                    # 不在最近消息集合中的记录视为窗口扩展出来的片段。
                    is_window_expanded=record.message_id not in recent_message_ids,
                )
            )
        # 返回转换好的证据块列表。
        return evidence_blocks

    def _convert_history_results_to_evidence(self, results: tuple[HistorySearchResult, ...]) -> list[ContextEvidenceBlock]:
        # 初始化工具历史证据块列表。
        evidence_blocks: list[ContextEvidenceBlock] = []
        # 遍历每一个历史查询结果。
        for result in results:
            # 从记录内容中读取 text 字段。
            text_value = result.record.content.get("text")
            # 只保留可读字符串内容。
            content_text = text_value.strip() if isinstance(text_value, str) else ""
            # 空内容结果直接略过。
            if not content_text:
                continue
            # 历史查询工具已经带有命中方式信息，这里直接保留下来。
            evidence_blocks.append(
                ContextEvidenceBlock(
                    # 写入命中消息 ID。
                    message_id=result.record.message_id,
                    # 写入命中消息类型。
                    message_type=result.record.message_type,
                    # 写入命中消息时间。
                    message_time=result.record.message_time,
                    # 写入文本内容。
                    content_text=content_text,
                    # 显式标为历史查询来源。
                    source="history_search",
                    # 保留全文命中标记。
                    matched_by_text=result.matched_by_text,
                    # 保留语义命中标记。
                    matched_by_vector=result.matched_by_vector,
                    # 工具历史结果默认不是窗口扩展片段。
                    is_window_expanded=False,
                )
            )
        # 返回转换好的工具历史证据块列表。
        return evidence_blocks

    def _deduplicate_evidence(self, evidence_blocks: list[ContextEvidenceBlock] | tuple[ContextEvidenceBlock, ...]) -> tuple[ContextEvidenceBlock, ...]:
        # 用消息 ID 做键，合并重复命中的证据。
        deduplicated: dict[str, ContextEvidenceBlock] = {}
        # 逐条处理证据块。
        for block in evidence_blocks:
            # 查询这条消息是否已经出现过。
            existing = deduplicated.get(block.message_id)
            # 首次出现时直接落入字典。
            if existing is None:
                # 首次出现的消息直接保留。
                deduplicated[block.message_id] = block
                continue
            # 同一条消息被多路命中时，合并命中来源和窗口信息。
            deduplicated[block.message_id] = ContextEvidenceBlock(
                # 消息 ID 保持不变。
                message_id=block.message_id,
                # 消息类型沿用当前块。
                message_type=block.message_type,
                # 时间取较新的那个，保证排序稳定。
                message_time=max(existing.message_time, block.message_time),
                # 内容优先保留已有内容，空时再回退到当前块内容。
                content_text=existing.content_text or block.content_text,
                # 来源暂时沿用已有来源，避免重复覆盖。
                source=existing.source,
                # 全文命中标记按或逻辑合并。
                matched_by_text=existing.matched_by_text or block.matched_by_text,
                # 语义命中标记按或逻辑合并。
                matched_by_vector=existing.matched_by_vector or block.matched_by_vector,
                # 窗口扩展标记按或逻辑合并。
                is_window_expanded=existing.is_window_expanded or block.is_window_expanded,
            )
        # 最终按时间顺序整理，方便 formatter 输出稳定的历史参考块。
        return tuple(
            # 对合并后的证据块按时间和消息 ID 排序。
            sorted(
                deduplicated.values(),
                key=lambda block: (block.message_time, block.message_id),
            )
        )
