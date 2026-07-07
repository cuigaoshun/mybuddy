from __future__ import annotations

from loguru import logger
from app.agent.context.tools.selector import build_category_selector_tool
from langchain_core.messages import AIMessage
from app.agent.util import extract_reply_text

from app.agent.graph.runtime import GraphRuntimeContext

from .. import helpers
from ..state import ReplyState


def tool_selector_node(state: ReplyState, context: GraphRuntimeContext) -> ReplyState:
    # 先拿到核心工具规格，这些工具允许 selector 直接命中并执行。
    core_tool_specs = context.tool_registry.list_core_tool_specs()
    # 提取核心工具对象，用于 bind_tools。
    core_tools = [tool_spec.tool for tool_spec in core_tool_specs]
    # 提取核心工具名称，主要用于日志展示。
    core_tool_names = tuple(tool_spec.name for tool_spec in core_tool_specs)
    # 构建一个“只负责选工具大类”的 selector 工具。
    selector_tool = build_category_selector_tool(context.tool_registry.list_non_core_categories())
    # selector 阶段绑定的是“工具大类选择器 + 核心工具”。
    selector_model = context.llm_provider.model().bind_tools([selector_tool, *core_tools])
    # 组装 selector 专用提示词消息。
    messages = helpers.build_selector_messages(state, context)
    # 调用 selector 模型，判断这轮是直答、直调核心工具，还是先选工具大类。
    reply = helpers.invoke_model(model=selector_model, messages=messages, bound_tool_names=("select_tool_category", *core_tool_names))
    # 尝试从 tool_calls 里提取被选中的工具大类。
    selected_category = helpers.extract_selected_category(reply)
    # 把 selector 输入消息和回复一起沉淀进状态，供后续节点继续用。
    updated_messages = tuple([*messages, reply])
    # 如果除了 selector 之外还出现了真实工具调用，说明模型直接命中了核心工具。
    if _has_non_selector_tool_call(reply):
        logger.info("tool_selector 直接命中核心工具调用")
        return state.model_copy(
            update={
                # 保留本轮 selector 输入与回复消息。
                "messages": updated_messages,
                # 既然已经直调核心工具，就不再保留工具大类选择结果。
                "selected_tool_categories": (),
                # 同理也清空工具名称集合。
                "selected_tool_names": (),
                # 对核心工具直调给一个较高置信度。
                "selector_confidence": 0.9,
                # 标记下一跳应直接执行工具。
                "selector_requires_tool_execution": True,
            }
        )
    # 尝试提取当前回复里的直接自然语言回答。
    direct_reply_text = _extract_direct_reply_text(reply)
    # 如果已经能直接回复用户，就在这里结束当前轮。
    if direct_reply_text is not None:
        logger.info("tool_selector 已直接产出最终回复，结束当前轮")
        return state.model_copy(
            update={
                # 保留本轮 selector 输入与回复消息。
                "messages": updated_messages,
                # 直接回复文本写入 final_reply。
                "final_reply": direct_reply_text,
                # 不再需要工具大类状态。
                "selected_tool_categories": (),
                # 不再需要工具名称状态。
                "selected_tool_names": (),
                # 对直答结果给满置信度。
                "selector_confidence": 1.0,
                # 既然已经直答，就不需要执行工具。
                "selector_requires_tool_execution": False,
            }
        )
    # 如果没有选中工具大类，也没有直接回复或核心工具调用，就按“继续直答”准备后续链路。
    if selected_category is None:
        logger.info("tool_selector 未选择工具大类，当前轮按直答继续")
        return state.model_copy(
            update={
                # 保留本轮 selector 输入与回复消息。
                "messages": updated_messages,
                # 清空工具大类选择结果。
                "selected_tool_categories": (),
                # 清空工具名称集合。
                "selected_tool_names": (),
                # 给一个较低置信度，表示 selector 没有明确决策。
                "selector_confidence": 0.4,
                # 不触发直接工具执行，后续将走工具展开/主模型路径。
                "selector_requires_tool_execution": False,
            }
        )
    # 如果明确选中了工具大类，就展开该类别下的工具规格列表。
    tool_specs = context.tool_registry.list_tool_specs_by_category(selected_category)
    # 提前提取工具名称，方便日志和状态调试。
    selected_tool_names = tuple(tool_spec.name for tool_spec in tool_specs)
    logger.info("tool_selector 选中工具大类={} tools={}", selected_category, selected_tool_names)
    return state.model_copy(
        update={
            # 写入本轮选中的单个工具大类。
            "selected_tool_categories": (selected_category,),
            # 写入该大类下已解析出的工具名称集合。
            "selected_tool_names": selected_tool_names,
            # 对选中结果给较高置信度。
            "selector_confidence": 0.9,
            # 这里只是选大类，不是直接执行工具。
            "selector_requires_tool_execution": False,
        }
    )


def _has_non_selector_tool_call(reply: AIMessage) -> bool:
    # 检查 selector 回复里是否混入了真实工具调用。
    for tool_call in getattr(reply, "tool_calls", []) or []:
        # 读取工具名字段。
        tool_name = tool_call.get("name")
        # 只要不是 select_tool_category，就视为真实工具调用。
        if isinstance(tool_name, str) and tool_name != "select_tool_category":
            return True
    # 否则说明只有 selector 调用或完全没有工具调用。
    return False


def _extract_direct_reply_text(reply: AIMessage) -> str | None:
    # 只要模型发起了任何 tool_call，就不能把它视为直接自然语言回复。
    if getattr(reply, "tool_calls", None):
        return None
    # 提取模型自然语言文本并去掉两端空白。
    reply_text = extract_reply_text(reply).strip()
    # 空文本不视为合法直接回复。
    if reply_text == "":
        return None
    # 返回可直接发给用户的回复文本。
    return reply_text
