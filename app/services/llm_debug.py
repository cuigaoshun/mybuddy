from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from loguru import logger

from app.util import extract_reply_text, format_messages_for_log


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

        del run_id, parent_run_id, tags, metadata
        model_name = serialized.get("name") or serialized.get("id") or "chat_model"
        bound_tool_names = _extract_bound_tool_names(serialized=serialized, extra_kwargs=kwargs)
        for index, batch_messages in enumerate(messages, start=1):
            logger.info(
                "模型开始调用，model={} batch={} tools={}\n{}",
                model_name,
                index,
                bound_tool_names,
                format_messages_for_log(list(batch_messages)),
            )

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


def _extract_bound_tool_names(serialized: dict[str, Any], extra_kwargs: dict[str, Any]) -> list[str]:
    """尽量从 callback 提供的信息里提取当前绑定给模型的工具名称。"""

    invocation_params = extra_kwargs.get("invocation_params")
    if isinstance(invocation_params, dict) and "tools" in invocation_params:
        return _normalize_tool_names(invocation_params.get("tools"))
    if "kwargs" in serialized and isinstance(serialized["kwargs"], dict) and "tools" in serialized["kwargs"]:
        return _normalize_tool_names(serialized["kwargs"].get("tools"))
    if "tools" in serialized:
        return _normalize_tool_names(serialized.get("tools"))
    return []


def _normalize_tool_names(raw_tools: Any) -> list[str]:
    """把 callback 提供的 tools 结构尽量收敛成工具名列表。"""

    if not isinstance(raw_tools, list):
        return []
    tool_names: list[str] = []
    for tool_item in raw_tools:
        if isinstance(tool_item, dict):
            function_payload = tool_item.get("function")
            if isinstance(function_payload, dict):
                tool_name = function_payload.get("name")
                if isinstance(tool_name, str):
                    tool_names.append(tool_name)
                    continue
            tool_name = tool_item.get("name")
            if isinstance(tool_name, str):
                tool_names.append(tool_name)
                continue
        tool_name = getattr(tool_item, "name", None)
        if isinstance(tool_name, str):
            tool_names.append(tool_name)
    return tool_names
