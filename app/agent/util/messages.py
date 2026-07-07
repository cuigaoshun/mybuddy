from __future__ import annotations

import json

from langchain_core.messages import AIMessage, BaseMessage, message_to_dict


def messages_to_jsonable(messages: list[BaseMessage]) -> list[dict[str, object]]:
    return [message_to_dict(message) for message in messages]


def format_messages_for_log(messages: list[BaseMessage], compact: bool = True) -> str:
    if not compact:
        return json.dumps(messages_to_jsonable(messages), ensure_ascii=False, indent=2)

    lines: list[str] = []
    for index, message in enumerate(messages, start=1):
        role_name = getattr(message, "type", "unknown")
        content = _extract_message_content(message)
        if content:
            lines.append(f"{index}. [{role_name}] {content}")
            continue
        lines.append(f"{index}. [{role_name}] <empty>")
    return "\n".join(lines)


def extract_reply_text(reply: AIMessage) -> str:
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


def _extract_message_content(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
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
