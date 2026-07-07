from __future__ import annotations

from typing import Protocol, Sequence

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import LlmConfig
from .llm_debug import DebugHandler


class ChatModel(Protocol):
    def invoke(self, input: list[BaseMessage]) -> AIMessage:
        ...

    def bind_tools(self, tools: Sequence[object]) -> "ChatModel":
        ...

    def get_num_tokens_from_messages(self, messages: list[BaseMessage]) -> int:
        ...


def create_chat_model(config: LlmConfig) -> ChatOpenAI:
    return ChatOpenAI(
        model=config.model,
        api_key=SecretStr(config.api_key),
        temperature=config.temperature,
        base_url=config.base_url,
        callbacks=[DebugHandler()],
    )
