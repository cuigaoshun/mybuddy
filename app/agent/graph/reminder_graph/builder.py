from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.graph.reminder_graph.runtime import ReminderGraphRuntimeContext, ReminderGraphServices
from app.agent.graph.reminder_graph.state import ReminderGraphState
from app.storage.models import ASSISTANT_MESSAGE_TYPE, USER_MESSAGE_TYPE, MemoryRecord


def build_reminder_graph(services: ReminderGraphServices):
    """构建提醒发送前的内容组装图。"""

    runtime_context = ReminderGraphRuntimeContext(services=services)

    def load_reminder_context_node(state: ReminderGraphState) -> dict[str, object]:
        return {
            "schedule": state.schedule,
            "job": state.job,
            "conversation_context": state.conversation_context,
        }

    def render_reminder_node(state: ReminderGraphState) -> dict[str, object]:
        model = runtime_context.services.llm_provider.model()
        reply = model.invoke(_build_prompt_messages(state))
        final_text = reply.content.strip() if isinstance(reply.content, str) else ""
        return {"final_text": final_text or f"提醒你：{state.schedule.reminder_text}"}

    graph = StateGraph(ReminderGraphState)
    graph.add_node("load_reminder_context", load_reminder_context_node)
    graph.add_node("render_reminder", render_reminder_node)
    graph.add_edge(START, "load_reminder_context")
    graph.add_edge("load_reminder_context", "render_reminder")
    graph.add_edge("render_reminder", END)
    return graph.compile()


def _build_prompt_messages(state: ReminderGraphState) -> list[SystemMessage | HumanMessage]:
    schedule = state.schedule
    context = state.conversation_context
    lines = [
        "你负责给即将发送的定时提醒生成最终文案。",
        "要求：",
        "1. 语气自然，像同一段对话里的后续提醒。",
        "2. 核心提醒事项必须保留，不要改写成别的任务。",
        "3. 优先参考来源消息前后几句和最新对话，补一点自然衔接，但不要编造新事实。",
        "4. 输出只是一条可直接发送给用户的提醒文本，不要解释你的思考。",
        f"原始提醒事项：{schedule.reminder_text}",
    ]
    source_window_text = _format_records(context.source_window_records)
    latest_records_text = _format_records(context.latest_records)
    if source_window_text:
        lines.append("来源消息前后几句：")
        lines.append(source_window_text)
    if latest_records_text:
        lines.append("当前会话最新对话：")
        lines.append(latest_records_text)
    return [
        SystemMessage(content="\n".join(lines)),
        HumanMessage(content=f"请生成这次提醒要发送的最终文案：{schedule.reminder_text}"),
    ]


def _format_records(records: tuple[MemoryRecord, ...]) -> str:
    rendered_lines: list[str] = []
    for index, record in enumerate(records, start=1):
        text_value = record.content.get("text")
        if not isinstance(text_value, str) or text_value.strip() == "":
            continue
        role_name = _resolve_role_name(record)
        rendered_lines.append(
            f"{index}. 时间：{record.message_time.isoformat()}｜角色：{role_name}｜内容：{text_value.strip()}"
        )
    return "\n".join(rendered_lines)


def _resolve_role_name(record: MemoryRecord) -> str:
    if record.message_type == USER_MESSAGE_TYPE:
        return "用户"
    if record.message_type == ASSISTANT_MESSAGE_TYPE:
        return "助手"
    return "消息"
