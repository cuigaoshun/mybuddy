from __future__ import annotations

from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import LlmConfig


class ChatModel(Protocol):
    def invoke(self, input: list[BaseMessage]) -> AIMessage:
        ...

    def bind_tools(self, tools: list[object]) -> "ChatModel":
        ...

    def get_num_tokens_from_messages(self, messages: list[BaseMessage]) -> int:
        ...


def create_chat_model(config: LlmConfig) -> ChatOpenAI:
    return ChatOpenAI(
        model=config.model,
        api_key=SecretStr(config.api_key),
        temperature=config.temperature,
        base_url=config.base_url,
    )
