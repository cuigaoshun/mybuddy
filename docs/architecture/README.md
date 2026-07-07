## Agent 图整体重构方案

这份文档描述的是 `mybuddy` 下一步要把 `app/agent/graph/` 重写成什么样，而不是说当前代码已经完全长成这样。

这里的目标仍然是飞书场景下的陪伴型 Agent 最小闭环，不扩展到多平台，也不把问题写成通用大 Agent 框架。

但这次不是“小修小补”。这次要做的是一次面向 `app/agent/graph/` 主流程的大规模整体重构：旧图和旧节点只作为理解现状的参考，不作为必须兼容的骨架。真正保留的只有仓库边界本身，例如飞书接入方式、router 负责发送与收尾、memory 继续走抽象接口；图内部流程、节点职责、状态组织都可以按新方案重写。

## 这次重构要解决什么

当前图已经有最小可用能力，但主流程还是偏“两段式拼装”：

1. `app/router/session_manager.py` 调 `GraphChatAgent`。
2. `app/agent/graph/agent.py` 先在图外构建 `ContextBundle`。
3. `app/agent/graph/builder.py` 里运行 `input -> select_tool -> refresh_messages/reply/tool loop`。
4. `tool` 节点把工具结果补回上下文，`reply` 节点继续决定是否再调工具。

这条链路能工作，但还存在几个结构问题：

- 图外和图内的职责切分不够稳定，context、memory、tool policy 的边界偏散。
- `select_tool` 同时承担“路由决策”和部分工具策略语义，但还没有升级成更明确的 router 层。
- 工具执行、上下文回灌、状态更新虽然已经有最小实现，但还没有被提升成新的主结构中心。
- 后续想补 `rewrite`、`planner`、更细的 tool policy 时，容易继续把逻辑塞回 builder 或 node 内。

所以这次不再把现有图当作必须兼容的骨架，而是把它当作参考，按新的目标流程整体重定义图结构。

## 目标流程

目标图先按下面这条主链路组织：

1. `Load Conversation State`
2. `Load User Profile (Memory)`
3. `Rewrite / Canonicalize`
4. `Planner`
5. `Tool Selector`
6. `Tool Expansion Layer`
7. `Chat Model`
8. `Tool Executor`
9. `Context Update Layer`
10. `Decision: Need More Tool / Continue?`
11. 循环回 `Tool / Reply`，或直接结束

这份文档里的“重写”是指：未来图结构、节点命名、状态组织都朝这个模型对齐。

这次文档定义的目标不是“先搭骨架再补节点”，而是一次性把整条链路改成：

`Load State -> Load Memory -> Rewrite -> Planner -> Tool Selector -> Tool Expansion -> Chat Model -> Tool Executor -> Context Update -> Loop/End`

## 当前代码与目标图的映射

当前仓库里已经存在、并且可以作为这次整体重构输入参考的部分如下：

### 1. Conversation State

- 入口编排在 `app/router/session_manager.py`
- 图内状态目前在 `app/agent/graph/state.py`
- 用户消息模型来自 `app/event/models.py`
- 会话信息来自 `app/memory/session_info_service.py`

这部分说明“会话状态进入图”已经有最小实现，但目前状态还偏回复流程导向，后面要改成更明确的 runtime state。

### 2. Memory / User Profile

- 记忆服务在 `app/memory/service.py`
- 仓储抽象在 `app/memory/repositories.py`
- PG 实现在 `app/memory/postgres_repository.py`
- 当前 `app/agent/context/builder.py` 已经会预取最近消息、相似召回和历史工具结果

这里可以视作新图里的 `Load User Profile (Memory)` 和一部分 `Context Update Layer` 已经有底子。

但要注意：现在的 memory 更偏“对话上下文证据”和“历史消息检索”，还不是完整意义上的长期用户画像系统。文档里仍然要保持仓库事实，不把它写成已经有成熟 profile store。

### 3. Tool Selector / Chat Model / Tool Executor

- `app/agent/graph/nodes/selector/node.py` 是当前最接近 router agent 的节点
- `app/agent/graph/nodes/reply/node.py` 是当前正式回复节点
- `app/agent/context/tools/executor.py` 是当前工具执行器
- `app/agent/context/tools/registry.py` 是当前工具注册中心
- `app/agent/context/tools/history_tools/search_history.py` 和 `app/agent/context/tools/web_search_tools/search_web.py` 是现有具体工具

这几块说明当前仓库已经有：

- 工具分流
- 小工具执行
- 工具结果回写
- 工具后继续回复

所以新图虽然不是凭空设计，但重构方式应理解为“借鉴现有能力，重写图骨架”，而不是“在旧图上继续层层打补丁”。

## 新图要怎么拆层

新的图结构建议分成四层，而不是继续把所有东西糊在 `builder` 里。

### 第一层：Graph Runtime State

这一层只关心“这一轮图在流转什么状态”。

建议后续状态至少包含：

- `messages`
- `thread_id`
- `current_message`
- `memory_snapshot`
- `canonical_query`
- `plan_result`
- `selected_tool_categories`
- `selected_specific_tools`
- `active_tools`
- `tool_results`
- `final_reply`
- `loop_decision`

这意味着 state 本身也要整体重画，而不是继续围绕“reply_text / selected_tool_category / refresh_after_tool”做局部修补。

### 第二层：Graph Context / Runtime Dependencies

这一层只放节点共享依赖，不直接承载流程决策。

建议至少包含：

- `llm_provider`
- `memory_service`
- `session_info_service`
- `context_builder` 或等价 memory loader
- `tool_registry`
- `tool_executor`
- `message_formatter`
- `budgeter`

这里的原则是：

- node 统一只收 `state + context`
- 依赖通过 context 传递
- 工具集和模型派生通过 context 中的明确入口获取

### 第三层：Graph Nodes

新图里的节点职责建议如下。

#### `load_memory`

当前代码里，图已经不再保留单独的 `load_state` 节点，而是直接从 `load_memory` 开始构建初始上下文。

它不负责复杂思考，只负责把当前消息、会话信息和最近记忆整理进图状态。

#### `load_memory`

负责读取本轮需要的 memory 内容。

当前阶段先沿用现有策略：

- 最近消息
- 相似召回
- 必要时工具补证据

后续如果要把用户长期偏好、人物设定、长期事实拆开，也是在这一层扩展，而不是散落到 reply 节点。

#### `rewrite`

这个节点负责把用户当轮输入改写成更稳定的 canonical query。

它要承担的职责包括：

- 处理“它 / 那个 / 上次”这类指代
- 利用当前对话和用户记忆做补全
- 消除无意义歧义
- 产出下游 planner 和 selector 都能直接消费的结构化查询结果

#### `planner`

这个节点负责基于 rewrite 之后的查询、memory 结果和当前会话状态制定当轮策略。

它至少要输出：

- 是否需要工具
- 工具使用顺序或偏好
- 是否允许直接回复
- 是否需要进一步检索或补充上下文
- 当前轮的任务拆分结果

#### `tool_selector`

这是第一阶段必须真正落地的核心节点。

它接收：

- 原始或 canonical query
- memory 结果
- planner 输出（当前阶段可为空或最小结构）

它产出：

- `selected_tool_categories`
- `selected_specific_tools`
- `confidence`

这一步要和 `tool executor` 明确分开：selector 只负责决策，不负责执行。

#### `tool policy`

当前代码已经不再保留单独的 `tool_expansion` 层，而是把“当前轮到底开放哪些工具”收进选择策略本身：

- 核心工具常驻暴露给模型。
- 非核心工具先通过 `select_tool_category` 选出工具大类。
- 下一轮模型调用只绑定被选中类别下的工具。

也就是说，当前仓库实际落地的是“核心工具直达 + 非核心工具渐进式披露”的双轨结构，而不是旧方案里显式拆开的 `tool_expansion` 节点。

#### `chat_model`

这个节点只负责两件事：

- 基于当前消息和 active tools 做推理
- 决定返回最终回复，还是发起 tool call

它不负责真正执行工具，也不负责长期记忆写回。

#### `tool_executor`

当前代码里工具执行层已经改成两段：

- 核心工具直接走 LangGraph 原生 `ToolNode`。
- 非核心工具走一个很薄的动态执行节点，只负责按当前已解锁的工具名查 registry 并执行。

这意味着当前仓库已经不再以 `app/agent/context/tools/executor.py` 作为统一工具执行入口，旧的 `ToolDefinition.execute` 那套手写分发链也已经退场。

#### `context_update`

当前代码已经不再保留独立 `context_update` 节点，也不再把工具结果手工拼回提示词里。

现在的真实策略是：

- 初始上下文仍然由 `load_memory` 一次构建。
- 工具执行后的后续轮次主要依赖标准 `ToolMessage` 继续驱动模型。
- 如果后续真的需要把工具结果再沉淀成结构化上下文层，再考虑重新引入更正式的 `context_update` 层。

#### `decision`

这一层负责判断：

- 还要不要继续调工具
- 是否回到 `tool_selector`
- 是否继续走 `chat_model`
- 是否直接结束

它要直接承担完整 loop policy：

- 有 tool call 时进入 `tool_executor`
- 工具结果更新后判断是否重新规划、重新选工具或直接继续回复
- 没有后续工具需求且已有 final reply 时结束

### 第四层：Graph External Lifecycle

图外还保留三件事，不要塞回图里：

- 飞书消息发送
- 用户消息 / 助手消息入库
- 会话 reply 时间更新

这些仍然属于 `router` 和 `memory` 协作范围，不属于图内思考流程。

## 这次重构明确做什么

这次不是分阶段推进，而是一次性把主图切到下面这些节点：

1. `load_memory`
2. `tool_selector`
3. `chat_model`
4. `core_tools`
5. `dynamic_tools`

也就是说，当前这版已经落地成一个更收敛的主图：保留 `load_memory`、`tool_selector`、`chat_model`，并把工具执行拆成“核心 ToolNode / 非核心动态节点”两段，而不是继续维持旧的 `tool_expansion + context_update` 链路。

## 这次重构明确不做什么

为了避免目标失焦，这次整体重构仍然不扩展这些范围：

- subagent / delegation 体系
- 多步任务树编排系统
- 独立 summarization worker
- 通用多平台抽象
- 管理后台或运营后台能力

## 对当前模块的改造方向

### `app/agent/graph/`

这里会成为新图的核心落点。

建议后续按下面几个职责重新组织：

- `state.py`：图状态
- `runtime.py`：共享运行时依赖
- `nodes/`：按新流程拆节点
- `routes.py`：图条件路由
- `builder.py`：只负责编图，不再混业务细节

### `app/agent/context/`

这里后续不再承担“整个图的主编排角色”，而是收敛成下面几类能力：

- memory 内容组织
- 消息格式化
- prompt / budget 辅助
- context update 的底层拼装能力

换句话说，`context` 继续存在，但它不应该继续成为“memory + tools + graph policy”的总汇编层。

### `app/agent/context/tools/`

这里保留为工具定义与执行实现层：

- registry
- tool definitions
- executor

但图里的“tool selection policy”和“tool expansion policy”不应长期停留在这个目录里，而应该提升到 graph 层。

### `app/memory/`

这里继续保持抽象优先：

- 会话
- 消息
- 记忆
- 历史检索
- 未来如果有发送记录，也应该继续按仓储抽象落地

新图重写不改变这个边界，只改变“图怎样消费 memory”。

## 为什么要一次性整体重构

因为当前仓库已经有最小闭环，这次真正要解决的是“旧图骨架不适合继续扩展”。

如果还保留旧的 `input -> select_tool -> reply/tool` 主结构，再把 `rewrite`、`planner`、`tool_expansion`、`context_update` 一层层补进去，最后仍然会回到同一个问题：新能力只是被硬塞到旧图上，节点职责和状态结构会继续发散。

所以这次要直接把下面这些层一次性立起来：

- selector 是独立节点
- tool expansion 是独立节点
- tool executor 是独立节点
- context update 是独立节点
- rewrite 和 planner 也是正式节点
- 图外继续负责发送和持久化收尾

## 一个更接近目标的阶段性时序

重写后的主流程，应直接切换到下面这样：

1. Router 把用户消息交给 Graph Agent。
2. `load_memory` 读取最近消息、相似召回和必要的长期记忆片段。
3. `tool_selector` 决定当前轮是直接回复、直接命中核心工具，还是先选择非核心工具大类。
4. `chat_model` 基于当前已开放工具决定直接回复还是继续发起 tool call。
5. 如果调用核心工具，则进入 `core_tools`。
6. 如果调用已解锁的非核心工具，则进入 `dynamic_tools`。
7. 工具执行完成后继续回到 `chat_model`。
8. 没有后续工具需求时输出 final reply。
9. Router 负责发送回复、写回助手消息、更新会话信息。

## 文档结论

这次新图重写的核心，是一次性把图的骨架整体换对，而不是继续维护旧的 `input -> select_tool -> reply/tool` 结构。

对当前仓库来说，这次整体重构最重要的是把以下结构一次性立起来：

- `load_memory`
- `tool_selector`
- `chat_model`
- `core_tools`
- `dynamic_tools`

只要这个骨架整体切换完成，后面不管是补更强的记忆策略、更多工具、还是更复杂的计划节点，都有清楚的挂点，不会再把 `builder`、`reply_node` 或 `context_builder` 重新养成新的 God Object。
