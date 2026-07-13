from __future__ import annotations

from typing import Protocol, Sequence, TypeVar

from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import LlmConfig
from .llm_debug import DebugHandler

StructuredSchema = TypeVar("StructuredSchema", bound=BaseModel)


class StructuredChatModel(Protocol[StructuredSchema]):
    def invoke(self, input: list[BaseMessage]) -> StructuredSchema:
        ...


class ChatModel(Protocol):
    def invoke(self, input: list[BaseMessage]) -> AIMessage:
        ...

    def bind_tools(self, tools: Sequence[object]) -> "ChatModel":
        ...

    def with_structured_output(
        self,
        schema: type[StructuredSchema],
        *,
        method: str = "json_schema",
    ) -> StructuredChatModel[StructuredSchema]:
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
