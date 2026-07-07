from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from loguru import logger

from app.agent.util.messages import extract_reply_text, format_messages_for_log


class DebugHandler(BaseCallbackHandler):
    """统一打印模型输入输出，便于本地调试模型调用。"""

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """在聊天模型开始调用时打印输入消息。"""

        del run_id, parent_run_id, tags, metadata, kwargs
        model_name = serialized.get("name") or serialized.get("id") or "chat_model"
        for index, batch_messages in enumerate(messages, start=1):
            logger.info("模型开始调用，model={} batch={}\n{}", model_name, index, format_messages_for_log(list(batch_messages)))

    def on_llm_end(self, response: Any, *, run_id: Any, parent_run_id: Any | None = None, **kwargs: Any) -> Any:
        """在模型调用结束时打印输出内容。"""

        del run_id, parent_run_id, kwargs
        generations: Sequence[Any] = getattr(response, "generations", ())
        if not generations:
            logger.info("模型调用结束，但没有可打印的 generations")
            return
        for batch_index, batch_generations in enumerate(generations, start=1):
            for generation_index, generation in enumerate(batch_generations, start=1):
                message = getattr(generation, "message", None)
                if message is None:
                    logger.info("模型调用结束，batch={} generation={} output={}", batch_index, generation_index, generation)
                    continue
                logger.info(
                    "模型调用结束，batch={} generation={} text={} tool_calls={}",
                    batch_index,
                    generation_index,
                    extract_reply_text(message),
                    getattr(message, "tool_calls", []),
                )
