# 定时提醒设计方案

## 背景

目标是在现有聊天后端里增加一类可延后执行的提醒能力，支持至少这些典型表达：

- `10 分钟后提醒我开会`
- `每周提醒我提交周报`
- `每周二 3 点提醒我开会`
- `每 8 小时提醒我喝水`

这类能力和即时问答不同。即时问答沿当前入站消息链路完成一次回复即可，提醒能力则要求系统先理解用户意图、把计划持久化、等待未来某个时间点，再主动向用户发出一条消息。

因此，提醒能力不能简单塞进现有 route 或同步聊天回复逻辑里，而需要一条独立的后台执行链路。

## 设计目标

本方案只覆盖当前最小闭环，不扩成完整日历系统。

目标包括：

1. 用户可在聊天中创建一次性提醒和受频率约束的重复提醒。
2. 提醒请求写入 PostgreSQL，重启后不丢失。
3. 后台 worker 可周期扫描应执行的提醒。
4. 提醒触发时通过独立 graph 组装最终提醒文案。
5. 最终发送仍复用现有 IM 出站链路。

本阶段支持的重复提醒范围应限制为：

- 按周重复，例如 `每周提醒我提交周报`
- 按周内具体时间重复，例如 `每周二 3 点提醒我开会`
- 固定间隔重复，例如 `每 8 小时提醒我喝水`

频率约束：

- 固定间隔类提醒最低间隔为 `8 小时`
- 任何规则如果换算后的执行频率高于 `每 8 小时一次`，都应拒绝创建

本阶段不覆盖：

- 完整自然语言时间解析体系
- 月提醒、工作日提醒等更复杂规则
- 用户级时区管理界面
- 提醒列表查询、修改、删除的完整交互

## 边界约束

当前仓库边界已经比较明确，这个方案必须贴着现有结构走。

1. `SessionManager` 是统一聊天编排入口，但它适合处理入站用户消息，不适合直接承担未来时点的主动提醒发送。
2. `bootstrap` 只负责 wiring 和生命周期管理，不承接提醒业务判断。
3. `router` 和 `gateway` 不适合放长时间等待逻辑，也不适合放 reminder 的核心业务逻辑。
4. 持久化能力应继续遵循 `service` / `repository` 分层，不在工具层直接拼 SQL。
5. 提醒触发后的出站发送应复用现有 `MessageSender` / `CompositeMessageSender`，避免平台逻辑分叉。

## 总体方案

方案分成四段：创建、存储、调度、执行。

### 1. 创建阶段

用户消息仍走现有主聊天链路：

`gateway -> event bus -> SessionManager -> chat agent -> main graph`

在主图里新增一个 reminder tool。这个工具只负责：

- 接收模型已经结构化好的提醒参数
- 补齐当前会话上下文中的用户和路由信息
- 调用 reminder service 写入 PostgreSQL
- 返回一段确认文案给当前会话

这个工具不做任何等待、轮询、未来发送，也不在工具里直接碰平台 SDK。

### 2. 存储阶段

提醒信息写入 PostgreSQL，两类数据分开保存：

- `schedule`：保存提醒规则
- `job`：保存待执行实例

这样做是为了把“提醒定义”与“某次实际执行”解耦。

一次性提醒可以在创建 `schedule` 后立即生成一条 `job`。重复提醒则只保存规则和下一次执行时间，由后台 worker 在合适时机继续物化后续 `job`。

### 3. 调度阶段

新增一个 worker，形状参考当前 `memory_scheduler.py`：

- 使用 `AsyncIOScheduler` 定时触发扫描
- 每次扫描 PostgreSQL，找出到期 reminder job
- 对 recurring schedule 先物化新 job
- 对待执行 job 做租约认领，避免并发重复发送

这个 worker 的职责只是调度和触发执行，不负责生成最终文案。

### 4. 执行阶段

worker 认领到 job 后，不直接拼最终发送文本，而是调用一个新的 `reminder graph`。

这个 graph 的职责是：

- 读取 reminder schedule 和 job 数据
- 按需要补充会话上下文、记忆上下文或用户信息
- 生成最终提醒文案

graph 返回文本后，再由执行服务构造 `OutChatMessage`，走现有 sender 出站，并在发送成功后补写 assistant memory。

## 推荐的数据模型

### reminder_schedule

建议保存以下字段：

- `id`
- `user_id`
- `im_type`
- `chat_id`
- `third_party_user_id`
- `chat_type`
- `reminder_text`
- `timezone`
- `run_at`，一次性提醒使用
- `cron_expr`，重复提醒使用
- `next_run_at`
- `status`，例如 `active`、`paused`、`cancelled`
- `source_message_id`
- `source_message_time`
- `source_text`
- `last_triggered_at`
- `created_at`
- `updated_at`

### reminder_job

建议保存以下字段：

- `id`
- `schedule_id`
- `scheduled_for`
- `status`，例如 `pending`、`running`、`sent`、`retryable_failed`、`blocked_user_route`、`failed`
- `lease_owner`
- `lease_until`
- `attempt_count`
- `available_at`
- `last_error`
- `dedupe_key`
- `sent_message_id`
- `sent_at`
- `created_at`
- `updated_at`

`schedule` 保存规则，`job` 保存某一次实际执行，这样后续做重试、失败记录、幂等控制会更清楚。

## 代码落点建议

### 主图工具

新增 reminder tool，位置建议放在现有工具体系下：

- `app/agent/context/tools/...`
- 在 `app/agent/graph/main_graph/builder.py` 注册

工具输入建议尽量结构化，至少包括：

- `action`，当前阶段可先固定为 `create`
- `reminder_text`
- `run_at` 或 `cron_expr`

工具实现中再从当前 `ReplyState` 或 runtime 上下文补齐：

- `user_id`
- `im_type`
- `chat_id`
- `third_party_user_id`
- `chat_type`
- 原始消息信息

其中 reminder 默认统一按 `Asia/Shanghai` 解释时间；重复提醒的创建阶段要做频率校验，凡是高于 `每 8 小时一次` 的规则一律拒绝。

### storage 层

继续遵循当前仓库风格：

- 在 `app/storage/repositories.py` 定义 reminder repository 协议
- 在 `app/storage/postgres/` 落 PostgreSQL 实现
- 在 `app/storage/` 下新增 `ReminderService`

`ReminderService` 负责：

- 校验 reminder tool 输入
- 归一化时间表达
- 计算 `run_at`、`cron_expr`、`next_run_at`
- 校验重复提醒频率不高于 `每 8 小时一次`
- 创建 schedule 和 job
- 物化 recurring job
- 认领 due job
- 更新发送结果状态

### reminder graph

建议新增一套独立目录，例如：

- `app/agent/graph/reminder_graph/builder.py`
- `app/agent/graph/reminder_graph/runtime.py`
- `app/agent/graph/reminder_graph/state.py`

这个 graph 不负责调度，不负责直接发送消息，只负责根据 reminder 上下文输出最终要发给用户的文本。

### worker

建议新增一个 `ReminderSchedulerRunner`，放在 `app/workers/`。

每个 tick 做两件事：

1. 扫描 due recurring schedule，物化新的 job。
2. 扫描 due job，做租约认领并执行。

worker 自身不应包含复杂文案逻辑，它只做调度、认领和调用执行服务。

### container 和生命周期

依赖注册继续放在 `app/bootstrap/container.py`，包括：

- reminder repository
- reminder service
- reminder graph services
- reminder graph
- reminder execution service
- scheduler
- runner

生命周期启动仍放在 `app/bootstrap/application.py`，只负责启动和停止 runner，不放 reminder 业务判断。

## 运行时流程

### 一次性提醒

1. 用户发送 `10 分钟后提醒我开会`。
2. 主图识别这是 reminder 创建意图。
3. reminder tool 被调用。
4. tool 调用 `ReminderService`，写入一条 `schedule` 和一条 `job`。
5. 当前聊天立即收到确认回复。
6. worker 在未来扫描到这条 due job。
7. 执行服务调用 `reminder graph` 生成最终提醒文本。
8. sender 发消息给用户。
9. 发送成功后写入 assistant memory，并将 job 标记为 `sent`。

### 重复提醒

1. 用户发送 `每周二 3 点提醒我开会`，或 `每 8 小时提醒我喝水`。
2. reminder tool 先校验频率是否合法，再创建一条 recurring schedule，写入 `cron_expr` 和 `next_run_at`。
3. 当前聊天收到确认回复。
4. worker 扫描到 schedule 到期，先物化一条新的 job。
5. worker 认领 job 并执行。
6. 发送成功后，更新 job 状态，同时推进 schedule 的下一次 `next_run_at`。

## 为什么不直接复用 SessionManager 发送提醒

`SessionManager` 现在的职责是处理入站聊天消息。

它会：

- 先写入用户消息记忆
- 抢 reply lease
- 调 chat agent 生成回复
- 发送回复后再写 assistant memory

主动提醒和这个语义不同。未来触发的一条提醒不是用户刚刚发来的新消息，如果硬复用 `SessionManager`，会把主动提醒错误地包装成一次入站聊天流程，导致状态和记忆语义都不干净。

因此提醒触发阶段应复用出站 sender 和 memory 写入能力，但不复用整个 `SessionManager.handle_message()`。

## 发送上下文的特殊约束

这是当前方案里最需要提前说明的风险点。

提醒是未来时点主动发送，创建 reminder 时拿到的即时上下文不适合直接固化进 `reminder_schedule`。发送阶段应基于 `user_id` 重新查询该用户当前可用的发送路由和平台运行态，再决定如何下发消息。

因此 phase 1 里建议：

1. `reminder_schedule` 只保存稳定的业务路由信息，例如 `user_id`、`im_type`、`chat_id`、`third_party_user_id`。
2. 触发执行时，先根据 `user_id` 查询用户当前可用的发送身份和平台运行态。
3. 对微信这类依赖运行时上下文的平台，由 sender 或上层执行服务在发送前动态解析所需上下文。
4. 若当前查不到可用发送路由或运行态，把 job 标记为 `blocked_user_route`，允许有限重试。
5. 超过重试窗口后标记为 `failed`，不要静默吞掉。

这样至少可以保证系统行为是可观察、可追踪的。

## 时区策略

当前仓库没有成熟的用户级时区体系，因此建议第一阶段不要直接扩成复杂设计。

更稳妥的做法是：

- 增加一个 app 级 `default_timezone`
- 创建 reminder 时把该时区持久化到 schedule
- 数据库存储统一使用 UTC
- `每周二 3 点` 这类规则按 `timezone + cron_expr` 计算下一次触发时间
- `每 8 小时` 这类规则按固定间隔推进 `next_run_at`

后续如果要支持用户级时区，再扩 user profile 或单独配置即可。

## 幂等与并发控制

提醒系统天然会遇到重复扫描、进程重启、worker 重入等问题，因此需要数据库级控制。

建议包含这些机制：

1. `job` 有唯一 `dedupe_key`。
2. 认领执行时使用租约字段，例如 `lease_owner` 和 `lease_until`。
3. 查询待执行 job 时使用数据库级排他控制，避免同一条 job 被多个 worker 同时发送。
4. 发送成功后立即更新状态，避免下一轮重复命中。

这类控制应该落在 repository 和 service 层，而不是散落在 graph 或 sender 中。

## 推荐的实现顺序

为了减少改动风险，建议按下面顺序实现：

1. 增加 reminder config、数据模型和 repository 协议。
2. 增加 PostgreSQL repository，实现 schedule/job 的建表与读写。
3. 增加 `ReminderService`，完成时间归一化、规则创建、job 物化、认领和状态更新。
4. 在主图里注册 reminder tool，使用户可以创建提醒。
5. 新增 `reminder graph` 和执行服务。
6. 新增 `ReminderSchedulerRunner` 并接入应用生命周期。
7. 手工验证一次性提醒、每周提醒、固定间隔提醒、失败重试和用户路由缺失场景。

## 当前结论

这个方案的核心思想是：

- 创建提醒走主图 tool
- 提醒规则和执行实例都写 PostgreSQL
- 到期扫描由独立 worker 负责
- 文案生成由独立 reminder graph 负责
- 实际发送继续复用现有 sender 链路

这样既能满足“10 分钟后提醒我”、“每周二 3 点提醒我”与“每 8 小时提醒我”的需求，又不会打破当前仓库已经形成的分层边界。

当前它仍是设计方案，不代表仓库已经实现该能力。
