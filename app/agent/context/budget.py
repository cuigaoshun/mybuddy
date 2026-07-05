from __future__ import annotations

from langchain_core.messages import BaseMessage

from app.services.llm import ChatModel


class ContextMessageBudgeter:
    def __init__(self, chat_model: ChatModel, max_tokens: int = 4000) -> None:
        self._chat_model = chat_model
        self._max_tokens = max_tokens

    def trim_messages(self, messages: tuple[BaseMessage, ...]) -> tuple[BaseMessage, ...]:
        # 先复制一份消息列表，后续按预算逐步裁剪动态消息。
        trimmed_messages = list(messages)
        while len(trimmed_messages) > 2 and self._count_tokens(trimmed_messages) > self._max_tokens:
            removed = False
            for index in range(len(trimmed_messages) - 2, 0, -1):
                message_type = getattr(trimmed_messages[index], "type", "")
                if message_type == "system":
                    # 系统层消息默认不裁，优先保留稳定前缀和规则说明。
                    continue
                # 从尾部向前裁动态消息，尽量少破坏前缀和最近提问位置。
                del trimmed_messages[index]
                removed = True
                break
            if not removed:
                break
        return tuple(trimmed_messages)

    def _count_tokens(self, messages: list[BaseMessage]) -> int:
        # token 预算统一走模型侧实现，避免本地估算和真实计数偏差过大。
        return self._chat_model.get_num_tokens_from_messages(messages)
