from app.agent.graph.state import ReplyState
from langchain.tools import ToolRuntime


def get_reply_state(runtime: ToolRuntime) -> ReplyState | None:
    """从 ToolRuntime 中安全读取当前 ReplyState。"""

    state = runtime.state
    if not isinstance(state, ReplyState):
        return None
    return state
