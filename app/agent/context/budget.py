from __future__ import annotations

from langchain_core.messages import BaseMessage

from app.services.llm import ChatModel


class ContextMessageBudgeter:
    """按模型 token 预算裁剪消息序列，尽量保留稳定前缀与最近问题。"""

    def __init__(self, chat_model: ChatModel, max_tokens: int = 4000) -> None:
        # 保存模型实例，统一复用它的真实 token 计数能力。
        self._chat_model = chat_model
        # 保存允许的最大 token 预算。
        self._max_tokens = max_tokens

    def trim_messages(self, messages: tuple[BaseMessage, ...]) -> tuple[BaseMessage, ...]:
        # 先复制一份消息列表，后续按预算逐步裁剪动态消息。
        trimmed_messages = list(messages)
        # 只要消息仍超预算，且还有可裁剪空间，就持续裁剪。
        while len(trimmed_messages) > 2 and self._count_tokens(trimmed_messages) > self._max_tokens:
            # 用 removed 标记这一轮是否真的删掉了某条消息。
            removed = False
            # 从倒数第二条开始往前找可裁剪消息，尽量保留最后提问。
            for index in range(len(trimmed_messages) - 2, 0, -1):
                # 读取消息类型，未知类型按空串处理。
                message_type = getattr(trimmed_messages[index], "type", "")
                # 系统消息不参与裁剪。
                if message_type == "system":
                    # 系统层消息默认不裁，优先保留稳定前缀和规则说明。
                    continue
                # 从尾部向前裁动态消息，尽量少破坏前缀和最近提问位置。
                del trimmed_messages[index]
                # 标记本轮已经发生裁剪。
                removed = True
                # 一轮只删一条，再重新计算 token。
                break
            # 如果这一轮一条都删不掉，就结束循环避免死转。
            if not removed:
                break
        # 返回裁剪后的不可变消息元组。
        return tuple(trimmed_messages)

    def _count_tokens(self, messages: list[BaseMessage]) -> int:
        # token 预算统一走模型侧实现，避免本地估算和真实计数偏差过大。
        return self._chat_model.get_num_tokens_from_messages(messages)
