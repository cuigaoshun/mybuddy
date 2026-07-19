# AGENTS.md

## OVERVIEW
- 这里只写 `app/agent` 子树规则，默认继承上层仓库约束。
- 这一层负责 LangGraph 图编排、提示上下文组装、工具元信息与工具暴露控制。
- 业务服务从 runtime context 注入进节点，节点层不要直接碰容器。

## STRUCTURE
- `graph/main_graph/`，回复生成主图，包含 `builder + runtime + state + nodes + routes/constants`。
- `graph/memory_graph/`，长期记忆处理图，包含固定线性节点链、运行时依赖和结构化输出 schema。
- `context/main_graph/`，主图上下文模型、system prompt、消息格式化。
- `context/memory_graph/`，长期记忆提取和合并提示词拼装。
- `context/tools/`，工具元数据、registry、类别选择器、tool runtime 辅助、具体工具家族。

## WHERE TO LOOK
- 看主图装配，先读 `graph/main_graph/builder.py`，再看 `runtime.py`、`state.py`、`routes.py`。
- 看主图入口封装，读 `graph/main_graph/agent.py`。
- 看长期记忆链路，读 `graph/memory_graph/builder.py`、`runtime.py`、`state.py`。
- 看主图上下文落成消息序列，读 `context/main_graph/formatter.py`、`context/main_graph/models.py`、`context/budget.py`。
- 看长期记忆提示词与结构化输出约束，读 `context/memory_graph/prompts.py` 和 `graph/memory_graph/state.py`。
- 看工具怎么注册和按类别开放，读 `context/tools/models.py`、`registry.py`、`selector.py`。
- 看具体工具家族，先读 `context/tools/history_tools/search_history.py` 和 `web_search_tools/search_web.py`。
- 要看当前图形结构而不是业务逻辑，跑 `graph/main_graph/render.py` 或 `graph/memory_graph/render.py`。

## CONVENTIONS
- graph builder 先组装 `LLMProvider`、services、formatter、budgeter、registry，再把节点函数包成闭包挂进 `StateGraph`。
- builder 只负责 wiring，不承载节点业务判断。节点实现留在 `nodes/`。
- 节点签名以 `state + injected context` 为主，返回 `dict[str, object]` 形式的增量更新。
- 主图的工具执行节点额外接 `Runtime`，其余节点只消费本地 runtime context。
- `ReplyState` 和 `MemoryGraphState` 是图内单一状态源。字段、枚举、schema 改动会联动 node、prompt、tool runtime、路由判断。
- 主图是有循环的，`chat_model -> execute_tools -> chat_model`，是否继续走工具由 `routes.py` 根据最后一个 `AIMessage.tool_calls` 决定。
- 记忆图不是循环图，是固定顺序流水线，`load_conversation -> extract_memory -> score_importance -> merge_memory -> save_memory`。
- 主图上下文先组 `ContextBundle`，再由 formatter 变成消息，再由 budgeter 按模型 token 预算裁剪。
- 长期记忆图的结构化输出 schema 统一收口在 `graph/memory_graph/state.py`，不要把提取结果字段散落到节点里各自定义。
- `ToolDefinition.build(...)` 是工具注册入口，产物必须是 `RegisteredTool`。
- `ToolRegistry` 既管名字索引，也管 category 索引和 core tool 索引。
- 非核心工具不是默认全开，先让模型调用 `select_tool_category` 写回 `selected_tool_category`，再按类别放行。
- `history_tools` 依赖当前 reply state 和 `ToolRuntime` 取会话身份，`web_search_tools` 只包外部搜索服务，当前标记为非核心工具。

## ANTI-PATTERNS
- 不要在 builder、runtime 里偷塞节点业务逻辑。
- 不要绕过 state 传临时字段，图内共享数据应先进 `ReplyState` 或 `MemoryGraphState`。
- 不要在多个节点重复声明结构化输出模型，尤其是长期记忆候选和用户画像 patch。
- 不要直接 new 裸工具后手工塞进执行层，统一走 `ToolDefinition.build(...) -> RegisteredTool -> ToolRegistry`。
- 不要把主图和记忆图混成一套抽象。两者执行形态不同，主图有工具回环，记忆图是线性处理。

## NOTES
- `ContextTool` 只是 formatter 和 budgeter 的薄聚合，不是额外业务层。
- `ConversationContextFormatter` 会把长期记忆、召回证据、最近消息、当前消息按固定顺序拼给模型，改顺序前先检查下游提示效果。
- `ToolCategoryName` 现在只声明 `history_tools`、`memory_tools`、`web_search_tools`。扩类目时要同时更新模型、selector、registry 使用面。
