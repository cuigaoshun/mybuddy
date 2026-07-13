# Memory Graph 中 extract / merge 节点交给 LLM 的改造方案

## 目标

把 `app/agent/graph/memory_graph/nodes.py` 里的 `extract_memory_node` 和 `merge_memory_node` 从当前的规则处理改为由 LLM 决策，同时尽量复用仓库现有的模型接入方式，保持 `memory_graph`、`agent`、`memory` 的边界不变。

这次改造的范围只聚焦两个节点：

- `extract_memory_node`：从会话消息中提取候选长期记忆。
- `merge_memory_node`：把旧的长期记忆摘要和新的重要候选记忆合并成新的长期记忆摘要。

不在这次范围内的内容：

- 不扩展到其他 IM 平台。
- 不重写整个 `memory_graph`。
- 不新增复杂后台流程。
- 不扩展到 `UserMemory` 之外的新记忆模型。

## 当前现状

当前 `memory_graph` 的处理方式比较直接：

1. `load_conversation_node` 读取上次处理后的新增消息。
2. `extract_memory_node` 逐条读取 `conversation_records` 里的文本内容。
3. 每条非空文本都会被直接包装成一个 `MemoryCandidate`，类别固定为 `conversation_summary`，重要度固定为 `1.0`。
4. `score_importance_node` 只做阈值过滤。
5. `merge_memory_node` 把旧 summary 和新候选按顺序拼接，最多保留前 20 行。

这种实现的优点是简单、稳定，但问题也比较明显：

- 提取阶段没有语义判断，用户的闲聊、重复表达、噪声内容都会被直接塞进候选记忆。
- 合并阶段没有压缩和归纳能力，summary 很容易变成机械拼接。
- 旧记忆和新消息之间没有真正的“整理”过程，更像是附加文本。

## 改造原则

### 1. 只让 LLM 负责语义决策

LLM 只负责：

- 从新增消息里提取候选长期记忆。
- 基于旧 summary 和新候选产出新的 summary。

以下内容仍然保留在本地代码里处理：

- `last_processed_message_id`
- `version`
- `created_at`
- `updated_at`
- `user_id`
- `im_type`

这样可以把模型输出限制在“记忆语义内容”层，避免把持久化生命周期字段交给 LLM，降低不可控性。

### 2. 复用现有 LLM 注入方式

主图 `main_graph` 现在已经有统一模型接入模式：

- 通过 `LLMProvider` 提供 `model()`。
- 在 graph runtime 中统一注入模型与服务。
- 节点只拿 runtime/context，不自己创建模型。

`memory_graph` 建议沿用同样思路，不要在 `nodes.py` 里直接调用 `create_chat_model`，也不要在节点里自己读配置。

### 3. prompt 渲染和节点执行分层

`nodes.py` 负责流程编排和结果落地。

prompt 组装应拆到 `app/agent/context/memory_graph/` 下的独立文件里，例如：

- `app/agent/context/memory_graph/render.py`
- 或 `app/agent/context/memory_graph/prompts.py`

这样可以保持和现有 `context` 分层一致：`context` 负责把图节点需要的输入组织成适合模型消费的内容，`nodes.py` 只负责节点执行、调用模型和落地结果。

### 4. 结构化输出优先，失败可降级

LLM 返回结果不能直接当自由文本使用，建议约束成固定结构：

- 提取阶段返回候选记忆数组。
- 合并阶段返回新的 summary 文本和结构化 `user_profile` 增量变更。

如果结构化解析失败，节点必须安全降级，不能因为模型返回异常内容导致整条记忆链路写坏。

## 推荐改造方案

## 一、运行时注入改造

在 `app/agent/graph/memory_graph/runtime.py` 中新增轻量 runtime context，直接复用现有 `LLMProvider`，让 `memory_graph` 可以拿到和 `main_graph` 一致的模型提供方式。

### 直接复用现有 `LLMProvider`

让 `memory_graph` runtime 也持有主图同款 `LLMProvider`。

优点：

- 复用现有模型抽象。
- `memory_graph` 和 `main_graph` 的模型使用方式一致。
- 改动面小。

建议效果：

- `extract_memory_node` 和 `merge_memory_node` 都通过 runtime context 中的 `llm_provider.model()` 取模型。

这里不建议再为 `memory_graph` 单独定义一套等价 provider。当前目标是最小落地，直接复用现有 `LLMProvider` 更简单，也更符合主图已经验证过的接入方式。

## 二、在 `context/memory_graph` 下增加独立的 prompt/render 层

建议在 `app/agent/context/memory_graph/` 下新增一个专门负责渲染输入的文件，职责只做两件事：

1. 把 `conversation_records` 渲染成适合提取候选记忆的输入。
2. 把旧 summary 与 `important_candidates` 渲染成适合合并摘要的输入。

建议至少拆出这两类函数：

- `render_extract_memory_prompt(...)`
- `render_merge_memory_prompt(...)`

其中渲染内容建议包含：

### 提取阶段输入

- 当前用户新增消息列表。
- 必要的消息角色信息，例如用户消息 / 助手消息。
- 明确要求 LLM 只提取适合长期保存的信息。
- 明确跳过寒暄、重复、一次性事务性噪声。

### 合并阶段输入

- 现有 `long_term_memory_summary`。
- 本轮筛出的 `important_candidates`。
- 明确要求输出“去重、归纳、压缩后的新 summary”。
- 明确要求保持稳定、克制，不发散编造。

## 三、extract_memory_node 改为 LLM 抽取候选记忆

### 目标

让 `extract_memory_node` 不再逐条原样收集文本，而是让 LLM 对本轮新增对话做语义抽取。

### 推荐输出结构

输出仍然映射回现有 `MemoryCandidate`：

- `category`
- `content`
- `importance`

建议类别先不要设计太复杂，保持当前最小闭环即可，例如仍以 `conversation_summary` 为主，后续再扩展。

### 节点内部流程建议

1. 如果 `conversation_records` 为空，仍然直接返回空候选。
2. 渲染提取 prompt。
3. 调用模型。
4. 解析结构化输出。
5. 映射成 `tuple[MemoryCandidate, ...]`。
6. 解析失败时返回空候选或进入保守降级分支。

### 为什么不直接返回自由文本

因为后面还有 `score_importance_node` 与 `merge_memory_node`，保留 `MemoryCandidate` 结构可以减少改动范围，也能保持 graph state 设计稳定。

## 四、merge_memory_node 改为 LLM 生成新 summary

### 目标

让 `merge_memory_node` 从“字符串拼接”变成“基于旧记忆和新候选的受约束重写”。

### 输入建议

- 旧的 `existing_user_memory.long_term_memory_summary`
- 旧的 `existing_user_memory.user_profile`
- `important_candidates`
- 可选：少量原始 `conversation_records` 文本，用于辅助模型理解上下文

### 输出建议

让模型返回两个字段：

- `long_term_memory_summary`
- `user_profile_patch`

不要让模型直接返回完整 `UserMemory`，也不要返回完整覆盖版 `user_profile`，因为 `UserMemory` 里与持久化、版本和处理进度相关的字段仍然应该由本地程序负责维护，而 `user_profile` 应以旧值为基础做增量合并。

### 节点内部流程建议

1. 如果没有新增消息，继续沿用现在逻辑，直接返回 `existing_user_memory`。
2. 如果没有 `important_candidates`，可以保守地保留旧 summary，只更新处理进度字段。
3. 渲染 merge prompt。
4. 调用模型生成新的 summary。
5. 解析结果后，用本地逻辑组装新的 `UserMemory`，其中 `long_term_memory_summary` 取模型结果，`user_profile` 由旧 profile 与 `user_profile_patch` 增量合并得到。
6. 解析失败时，降级为保留旧 summary，或者退回当前的拼接式 merge。

## 五、score_importance_node 先保持不动

当前 `score_importance_node` 只做阈值过滤：

- `importance >= 0.5` 保留。

如果提取节点已经由 LLM 输出 `importance`，那么这一步可以继续保留，不需要同时重构。这样有两个好处：

- 图结构不变。
- 提取与过滤职责仍然清楚。

后续如果发现 `importance` 实际上已经完全由提取 prompt 控制，再考虑是否把 `score_importance_node` 合并掉，但这不属于本次最小方案。

## 六、user_profile 也纳入本次 LLM 分支

这次方案里，`user_profile` 不再继续完全沿用旧值，但也不是让 LLM 每次生成整份覆盖结果，而是在 merge 阶段由 LLM 只返回需要更新的增量字段。

这样做的前提是范围要继续收紧：

1. 仍然只在 `merge_memory_node` 里生成，不新增额外 graph 节点。
2. 只生成现有 `UserMemoryProfile` 结构内的增量数据，不扩展新的 profile 字段体系。
3. 仍然由本地代码负责把模型结果映射并合并回 `UserMemoryProfile`，并维护其他系统字段。

因此本次建议：

- merge prompt 里显式提供旧 `user_profile`、旧 summary 和新候选记忆。
- 模型返回 `user_profile_patch`，只包含需要新增、更新或清空的字段。
- 本地代码先把 patch 映射为受限结构，再与旧 `user_profile` 合并；如果映射或校验失败，则保守回退到旧 `user_profile`。

### 推荐的 `user_profile_patch` 输出结构

模型输出的 `user_profile_patch` 必须严格对齐当前已有的 `UserMemoryProfile` 结构，不单独发明新的顶层字段，并且只返回需要变更的部分。

建议目标结构如下：

```json
{
  "preferences": {
    "喜欢的话题": "AI Agent",
    "作息偏好": "夜间活跃"
  },
  "relationship": {
    "affinity": {
      "notes": "用户愿意持续交流，并主动讨论项目细节"
    }
  }
}
```

这里的约束要和代码中的现有模型保持一致：

- `profile`：可选键值对对象，映射到 `UserMemoryAttributes`
- `preferences`：可选键值对对象，映射到 `UserMemoryAttributes`
- `relationship.affinity.level`：整数或空
- `relationship.affinity.confidence`：`0` 到 `1` 的浮点数或空
- `relationship.affinity.notes`：字符串或空

如果某一块没有变化，就不要返回该块。

### 字段级生成约束

为了避免模型把 `user_profile` 写散，prompt 里应明确这些规则：

1. 只返回需要新增、修改或清空的字段，不返回未变化字段。
2. `profile` 只放相对稳定的用户事实，例如身份、背景、长期状态。
3. `preferences` 只放用户偏好，例如喜欢的话题、交流方式、时间偏好。
4. `relationship.affinity` 只描述用户与 Agent 的互动状态，不要混入用户基础资料。
5. 没有足够把握时宁可不填，也不要猜测。
6. 新值与旧值冲突时，优先保守更新，避免频繁抖动。

### 清空语义

如果模型判断某个旧字段应该被移除，建议显式返回 `null` 表示清空，例如：

```json
{
  "preferences": {
    "旧偏好字段": null
  }
}
```

本地代码收到 `null` 后，再按合并规则删除对应字段，而不是把字符串 `"null"` 写进去。

### 本地映射规则

模型输出不会直接落库，而是要经过本地映射：

1. `profile` 和 `preferences` 的对象项逐条解析为 patch 项。
2. 值类型只允许 `str | bool | int | float | null`。
3. key 不能为空字符串，value 不能是数组或嵌套对象。
4. `relationship.affinity` 需要单独解析为 patch 结构。
5. patch 校验通过后，再与旧 `UserMemoryProfile` 做增量合并。
6. 合并完成后，再组装成最终 `UserMemoryProfile`。

### 本地合并规则

建议把合并逻辑固定成确定性规则：

1. patch 未出现的字段保持旧值不变。
2. patch 出现且值合法的字段覆盖旧值。
3. patch 出现且值为 `null` 的字段，从旧 profile 中删除。
4. `relationship.affinity` 按子字段粒度合并，不因为只更新 `notes` 就丢掉旧的 `level` 和 `confidence`。
5. 合并后如果某个对象为空，则按现有模型约定保留空结构。

### 推荐的回退策略

`user_profile` 建议采用“局部回退优先，整体回退兜底”的策略：

- `profile` patch 解析失败：保留旧 `profile`
- `preferences` patch 解析失败：保留旧 `preferences`
- `relationship.affinity` patch 解析失败：保留旧 `relationship`
- patch 整体结构完全不合法：回退到整个旧 `user_profile`

这样可以避免因为模型只写坏一个字段，就把整份画像全部丢掉。

### prompt 中应明确禁止的输出

为了减少脏数据，merge prompt 里最好明确禁止模型输出以下内容：

- 未在 `UserMemoryProfile` 中定义的顶层字段
- 数组类型属性值
- 多层嵌套对象属性值
- 基于猜测生成的隐私信息、身份信息或敏感标签
- 和当前对话无关的泛化人格描述
- 未变化字段的重复回传

## 七、失败与降级策略

LLM 引入后，必须提前定义失败策略。

建议按以下原则处理：

### 提取失败

- 返回空 `extracted_candidates`
- 不要抛出导致整条 memory graph 中断的异常

### 合并失败

- 优先保留旧 summary
- `user_profile` 优先保留旧值
- 或退回当前的拼接逻辑与旧 profile

### 共同原则

- 绝不写入结构不合法的 `UserMemory`
- 绝不把模型原始文本直接当成完整对象落库
- 绝不让模型决定 `version`、`created_at`、`updated_at` 等系统字段
- `user_profile` 任一字段不合法时，至少要支持局部或整体回退，不能把脏结构落库

## 文件级改动建议

如果按最小方案落地，建议涉及以下文件：

### 1. `app/agent/graph/memory_graph/runtime.py`

改动目标：

- 新增 `memory_graph` 的 runtime context。
- 直接复用现有 `LLMProvider`。

### 2. `app/agent/graph/memory_graph/nodes.py`

改动目标：

- `extract_memory_node` 改成调用 LLM 提取候选记忆。
- `merge_memory_node` 改成调用 LLM 生成新的长期记忆摘要和 `user_profile_patch`。
- 保留 `UserMemory` 的本地组装逻辑。

### 3. `app/agent/context/memory_graph/render.py` 或同类文件

新增目标：

- 负责提取和合并两个 prompt 的渲染。
- 合并 prompt 中明确描述 `UserMemoryProfile` 的目标结构与字段语义。
- 合并 prompt 中明确 `user_profile_patch` 的 JSON 输出格式、增量规则与禁止项。

### 4. `app/agent/graph/memory_graph/state.py`

改动目标：

- 如有需要，新增用于承接 merge 结构化结果的中间模型。
- 复用或补充 `UserMemoryProfile` 对应的本地校验入口。
- 明确 merge 结果至少包含 `long_term_memory_summary` 与 `user_profile_patch` 两部分。

### 5. `app/agent/graph/memory_graph/builder.py`

改动目标：

- 如果 runtime 注入方式有变化，需要把新的依赖透传给节点。

### 6. graph 装配入口相关文件

改动目标：

- 在构建 `memory_graph` 时，把当前全局 LLM provider 一并传入。

## 建议的实施顺序

建议按下面顺序做，而不是一次性混改：

1. 先给 `memory_graph` runtime 接上 LLM provider。
2. 在 `app/agent/context/memory_graph/` 下新增 prompt/render 文件。
3. 先改 `extract_memory_node`，保持 `merge_memory_node` 不动。
4. 再改 `merge_memory_node`。
5. 最后补失败降级逻辑。

这样每一步都比较小，也更容易确认问题出在哪一层。

## 这份方案的核心取舍

这次方案的核心不是“让 LLM 接管所有长期记忆逻辑”，而是把最需要语义判断的两步交给 LLM：

- 从对话中抽什么值得留下。
- 如何把新旧记忆整理成更稳定的摘要。
- 如何在现有 `UserMemoryProfile` 结构内增量更新用户画像。

与此同时，仓库里与持久化、版本、时间戳、用户身份有关的确定性逻辑继续保留在本地代码中。这种做法仍然保持改动集中，只是把 LLM 负责的语义输出从 summary 扩展到了 `user_profile`。

## 结论

推荐采用的最小落地路径是：

1. 直接复用现有 `LLMProvider` 注入到 `memory_graph`。
2. 在 `app/agent/context/memory_graph/` 下新增独立 render/prompt 层。
3. 让 `extract_memory_node` 通过 LLM 输出结构化 `MemoryCandidate`。
4. 让 `merge_memory_node` 通过 LLM 输出新的 `long_term_memory_summary` 和 `user_profile_patch`。
5. 继续由本地代码维护 `UserMemory` 其余字段与降级行为。

这样可以在不破坏当前模块边界的前提下，把“机械拼接型长期记忆”升级为“有语义提取和归纳能力的长期记忆整理流程”。
