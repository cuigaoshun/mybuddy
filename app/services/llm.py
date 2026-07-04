from __future__ import annotations

from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

from app.core.config import LlmConfig


class ChatModel(Protocol):
    def invoke(self, input: list[BaseMessage]) -> AIMessage:
        ...


def create_chat_model(config: LlmConfig) -> ChatOpenAI:
    kwargs: dict[str, object] = {
        "model": config.model,
        "api_key": config.api_key,
        "temperature": config.temperature,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return ChatOpenAI(**kwargs)
