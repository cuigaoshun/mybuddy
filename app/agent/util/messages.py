from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, message_to_dict


def messages_to_jsonable(messages: list[BaseMessage]) -> list[dict[str, object]]:
    # 统一转成可 JSON 序列化结构，便于日志打印。
    return [message_to_dict(message) for message in messages]


def extract_reply_text(reply: AIMessage) -> str:
    # 兼容不同模型返回的 content 结构，尽量稳定提取最终回复文本。
    content = reply.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
                continue
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    text_parts.append(text_value)
        return "\n".join(part for part in text_parts if part)
    return ""
