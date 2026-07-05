from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, message_to_dict

from app.agent.context.tools.models import ToolSpec


def messages_to_jsonable(messages: list[BaseMessage]) -> list[dict[str, object]]:
    # 统一转成可 JSON 序列化结构，便于日志打印。
    return [message_to_dict(message) for message in messages]


def tool_specs_to_jsonable(tool_specs: tuple[ToolSpec, ...]) -> list[dict[str, object]]:
    # 把当前绑定给模型的工具定义整理成可读结构，便于排查 schema 是否符合预期。
    tool_items: list[dict[str, object]] = []
    for tool_spec in tool_specs:
        args_schema = getattr(tool_spec.tool, "args_schema", None)
        schema_payload: dict[str, object] | None = None
        if args_schema is not None and hasattr(args_schema, "model_json_schema"):
            schema_payload = args_schema.model_json_schema()
        tool_items.append(
            {
                "category": tool_spec.category.name,
                "name": tool_spec.name,
                "description": tool_spec.description,
                "prompt_hint": tool_spec.prompt_hint,
                "args_schema": schema_payload,
            }
        )
    return tool_items


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
