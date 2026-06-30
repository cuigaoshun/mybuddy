from typing import List, Literal
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END


# =========================
# 1. 状态定义（BaseModel版）
# =========================
class State(BaseModel):
    messages: List[str]
    mood: str
    result: str


# =========================
# 2. 节点：用户输入处理
# =========================
def input_node(state: State):
    last_msg = state.messages[-1]

    return State(
        messages=state.messages,
        mood="neutral",
        result=f"收到消息：{last_msg}"
    )


# =========================
# 3. 节点：情绪分析
# =========================
def emotion_node(state: State):
    msg = state.messages[-1]
    mood = "happy" if "哈哈" in msg else "neutral"

    return state.model_copy(update={"mood": mood})


# =========================
# 4. 节点：回复生成
# =========================
def reply_node(state: State):
    reply = "看起来你心情不错 😄" if state.mood == "happy" else "我在听你说。"
    return state.model_copy(update={"result": reply})

# =========================
# 5. 路由函数
# =========================
def route(state: State) -> Literal["reply"]:
    return "reply"


# =========================
# 6. 构建图
# =========================
def build_graph():
    graph = StateGraph(State)

    graph.add_node("input", input_node)
    graph.add_node("emotion", emotion_node)
    graph.add_node("reply", reply_node)

    graph.add_edge(START, "input")
    graph.add_edge("input", "emotion")

    graph.add_conditional_edges("emotion", route)

    graph.add_edge("reply", END)

    return graph.compile()


# =========================
# 7. 运行
# =========================
def main():
    app = build_graph()

    # 画图
    # img_bytes = app.get_graph().draw_mermaid_png()
    # with open("graph.png", "wb") as f:
    #     f.write(img_bytes)

    # 运行
    result = app.invoke(
        State(
            messages=["哈哈你好"],
            mood="",
            result=""
        )
    )

    print("\n=== 输出 ===")
    print(result)


if __name__ == "__main__":
    main()