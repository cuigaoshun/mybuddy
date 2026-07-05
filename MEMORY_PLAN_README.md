# 对话记忆接入方案

本文档只描述一期“对话记忆”能力的接入方案，用于确认设计方向。当前不修改业务实现，只先把表结构、分层边界、写入时机和可替换抽象定义清楚。

## 目标

本次要补的是“对话记忆”最小闭环，范围限定为：

- 飞书收到用户消息后，保存一条“用户发来的消息记忆”。
- 飞书发送消息成功后，保存一条“系统回复给用户的消息记忆”。
- 每条记忆都生成文本向量，供后续检索使用。
- 底层先用 PostgreSQL 实现，但上层调用方不感知底层是 PG、pgvector 还是未来别的向量能力。

## 不变的分层边界

按照当前仓库约束，职责保持如下：

- `app/gateway/`：只负责飞书事件接入与字段归一化，不直接写数据库。
- `app/router/`：负责识别一次对话处理流程里何时读写记忆。
- `app/agent/`：只消费结构化记忆结果，不感知 PG、SQL、向量模型。
- `app/memory/`：统一暴露记忆写入、检索、向量化相关抽象与服务。
- `app/services/im_sender.py`：仍然只负责统一发消息，但在“发送成功”这个时点向上游返回记忆写入所需信息。
- `app/workers/`：后续可承接异步摘要、异步沉淀、重算向量等任务。

这次方案里，记忆能力的正式入口放在 `app/memory/`，而不是塞进 `gateway` 或 `services`。

## 现状判断

基于当前仓库代码，现有链路是：

1. `app/gateway/dispatcher.py` 接收飞书 websocket 消息。
2. 消息被转换为 `app/event/models.py` 中的 `IncomingChatMessage`。
3. `app/event/bus.py` 把消息发布给 `app/router/session_manager.py`。
4. `SessionManager` 调 `app/agent/graph.py` 生成回复。
5. `app/services/im_sender.py` 调飞书 SDK 发消息。

目前 `app/memory/service.py` 还是空文件，仓库里也还没有会话、消息、记忆、发送记录的仓储抽象，所以这次方案需要先补抽象，再补 PostgreSQL 实现。

## 记忆表设计

一期建议新增一张“对话记忆表”，先把你要求的字段完整落下。

表名改为：`chat_memory`

字段建议如下：

- `id`：主键，使用 `GENERATED ALWAYS AS IDENTITY`。
- `user_id`：用户标识，对飞书场景先保存内部统一用户 ID。当前链路里可先承接 `sender_id`。
- `type`：消息方向，`0` 表示 `user_id` 发来的消息，`1` 表示系统发给 `user_id` 的消息。
- `im_type`：IM 平台类型，一期固定可写 `feishu`，但字段保留，避免未来表结构重做。
- `message_time`：消息时间，数据库字段类型使用 `TIMESTAMP`。用户消息取飞书事件里的发送时间，系统回复取飞书发送成功返回或可拿到的发送时间；飞书原始值如果是毫秒时间，需要在写库前统一转换为时间戳。
- `content`：原始文本内容。
- `content_vector`：文本向量。

如果底层使用 `pgvector`，建议列定义为：

- `content_vector vector(384)`

因为 `SentenceTransformer` 模型 `paraphrase-multilingual-MiniLM-L12-v2` 输出维度是 `384`。

建议直接把建表 SQL 写成：

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chat_memory (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id text NOT NULL,
    type smallint NOT NULL,
    im_type text NOT NULL,
    message_time timestamp NOT NULL,
    content text NOT NULL,
    content_vector vector(384) NOT NULL
);

CREATE INDEX idx_chat_memory_user_id_im_type_message_time ON chat_memory (user_id, im_type, message_time);
CREATE INDEX idx_chat_memory_content_vector_hnsw
ON chat_memory
USING hnsw (content_vector vector_cosine_ops);
```

一期就直接加上 `hnsw` 向量索引。

## PostgreSQL 落地建议

虽然上层不能依赖 PG 细节，但一期底层实现建议直接采用：

- PostgreSQL
- `pgvector`
- `content_vector vector(384)`
- 相似度先按余弦距离设计

原因很直接：

- 这套方案足够轻，符合一期最小闭环目标。
- Postgres 既能承接结构化字段，也能先承接向量列，避免过早拆分存储系统。
- 后续如果要切到别的向量库，只需要替换 `memory` 基础设施实现，不需要改 `router` 和 `agent`。

一期数据量不大时，也按你的要求默认建好 `HNSW` 向量索引；普通索引只保留 `user_id + im_type + message_time` 联合索引。

## 配置项建议

当前 `config.toml:1` 里只有飞书配置。为了正式落地 PG，方案里建议把配置补成两组：

- `feishu`
- `postgres`

建议配置项如下：

```toml
[feishu]
app_id = ""
app_secret = ""
log_level = "INFO"

[postgres]
host = "127.0.0.1"
port = 5432
user = "postgres"
password = ""
database = "mybuddy"
schema = "public"
min_pool_size = 1
max_pool_size = 10
connect_timeout_seconds = 5
```

如果后续还是继续使用 `Dynaconf`，这些项也应该支持通过环境变量覆盖，例如：

- `MYBUDDY_POSTGRES__HOST`
- `MYBUDDY_POSTGRES__PORT`
- `MYBUDDY_POSTGRES__USER`
- `MYBUDDY_POSTGRES__PASSWORD`
- `MYBUDDY_POSTGRES__DATABASE`

## 抽象设计

为了让调用方不关心底层实现，建议在 `app/memory/` 下先定义三层抽象。

### 1. 记忆写入输入模型

定义一个内部统一写入模型，例如：

- `MemoryRecord`
  - `user_id`
  - `message_type`
  - `im_type`
  - `message_time`
  - `content`

这里不暴露任何 PG 字段类型，也不暴露向量库概念。

### 2. 向量生成抽象

定义一个嵌入提供者接口，例如：

- `EmbeddingProvider`
  - `embed_document(text: str) -> list[float]`
  - `embed_query(text: str) -> list[float]`
  - `dimension() -> int`
  - `model_name() -> str`

一期默认实现：

- `SentenceTransformerEmbeddingProvider`
- 模型固定为 `BAAI/bge-base-zh-v1.5`

这样以后如果要换模型，`router`、`agent`、`gateway` 都不用改。

### 3. 记忆仓储抽象

定义一个面向业务的仓储接口，例如：

- `ConversationMemoryRepository`
  - `save(record: MemoryRecord, vector: list[float]) -> None`
  - `list_recent_by_user(user_id: str, im_type: str, chat_id: str) -> list[MemoryRecord]`

一期最小闭环先实现 `save(...)` 和“按 `user_id + im_type` 读取最近 10 条会话”；更复杂的语义检索等后面接 RAG 时再补。

其 PostgreSQL 实现可以命名为：

- `PostgresConversationMemoryRepository`

这个实现里才允许出现：

- SQL
- `pgvector`
- 表名与索引细节

## 服务编排设计

在 `app/memory/` 再包一层服务，建议命名为：

- `ConversationMemoryService`

职责是：

1. 接收统一的 `MemoryRecord`
2. 调用 `EmbeddingProvider` 生成向量
3. 调用 `ConversationMemoryRepository` 完成持久化

上层只调用：

- `conversation_memory_service.store(record)`

这样调用方无需知道：

- 用的是 `SentenceTransformer` 还是别的模型
- 存的是 PG 普通表还是 PG + pgvector
- 后续是否切成异步写入

## 收消息写入时机

用户消息的记忆写入建议放在 `app/router/session_manager.py` 里，而不是直接写在 `gateway`。

原因是：

- `gateway` 负责平台适配，不应承担业务落库职责。
- `SessionManager` 已经是“收到统一消息后开始处理会话”的主编排点。
- 这里最容易保证后续接别的平台时依旧复用同一套记忆流程。

建议流程：

1. `FeishuDispatcher` 把飞书消息转成 `IncomingChatMessage`
2. `SessionManager.handle_message(...)` 收到统一消息
3. `SessionManager` 先构造一条 `type=0` 的 `MemoryRecord`
4. 调用 `ConversationMemoryService.store(...)`
5. 再继续走 Agent 回复流程

## 发消息写入时机

系统回复的记忆写入建议仍由 `SessionManager` 编排，但发送时间要由 `app/services/im_sender/` 这一组发送能力提供。

建议调整方向如下：

1. `FeishuMessageSender.send_text(...)` 不再只返回 `None`
2. 发送成功后，返回一个内部发送结果模型，例如：
   - `SentMessageResult`
   - 包含 `chat_id`
   - 包含 `message_id`（如果飞书返回里能取到）
    - 包含 `message_time`
   - 包含 `im_type`
   - 包含 `content`
3. `SessionManager` 拿到发送成功结果后，构造一条 `type=1` 的 `MemoryRecord`
4. 再调用 `ConversationMemoryService.store(...)`

这样做的关键点是：

- 飞书 SDK 细节仍封装在 `im_sender` 内。
- 记忆写入决策仍在 `router` 编排层。
- 上层可以基于统一发送结果模型写逻辑，而不是碰飞书 SDK 响应对象。

## 时间字段来源

你的要求是“飞书的收到消息和发送消息成功都拿到消息的发送时间，根据这个写表的创建时间”，这里建议明确成以下规则：

### 用户发来的消息

- 来源：飞书消息事件里的原始发送时间。
- 落库字段：`message_time`
- 单位：毫秒

这意味着 `IncomingChatMessage` 后续需要补一个统一字段，例如：

- `message_time: datetime`

如果飞书原始返回的是毫秒时间，则在进入内部统一模型前先完成转换。

### 系统发出的消息

- 来源：飞书发送成功后的返回结果里可获取的消息发送时间。
- 落库字段：`message_time`
- 单位：毫秒

如果飞书发送成功响应里拿不到服务端消息时间，则需要在实现阶段再确认飞书发送响应结构；但从方案层面，`MessageSender` 的返回模型必须为“发送成功后的时间信息”留字段，避免后续接口重构。

## 目录拆分建议

你点到的三个位置，当前都还是单文件结构。为了让后续记忆、PG 和平台能力继续扩展，方案里建议改成目录化组织。

### `app/bootstrap/`

现在 `app/bootstrap/feishu.py:1` 同时承担了：

- 读取配置
- 初始化日志
- 创建 `EventBus`
- 创建 `FeishuMessageSender`
- 创建 `SessionManager`
- 完成订阅关系
- 启动飞书 websocket 客户端

这里把 `bus` 的初始化直接写在飞书 boot 里，确实不太合理，因为它会让“平台启动”和“应用内部装配”耦在一起。

建议拆成：

- `app/bootstrap/app.py`
  - 负责组装应用内部依赖
  - 创建 `EventBus`
  - 创建 `ConversationMemoryService`
  - 创建 `SessionManager`
  - 返回应用装配结果
- `app/bootstrap/feishu.py`
  - 只负责飞书相关启动
  - 接收已经装配好的 `EventBus`、`SessionManager`、`MessageSender`
  - 创建并启动飞书 websocket 客户端

这样之后接入 PG 或别的基础设施时，不需要把所有应用内部依赖继续塞进飞书 boot。

### `app/gateway/dispatcher.py`

现在 `app/gateway/dispatcher.py:1` 是单文件。你要求改成 `dispatch` 是一个目录，这个方向是对的。

建议调整为：

- `app/gateway/dispatch/__init__.py`
- `app/gateway/dispatch/feishu.py`

其中：

- `feishu.py`
  - 放 `FeishuDispatcher`
  - 放飞书消息归一化逻辑
- `__init__.py`
  - 统一导出 dispatcher

这样后面如果还会出现别的平台 dispatcher，或者飞书里再拆 text/image/file 等消息适配逻辑，目录结构更稳，不需要把一个文件越堆越大。

### `app/services/im_sender.py`

现在 `app/services/im_sender.py:1` 也是单文件，后续如果要同时承接：

- 飞书发送实现
- 统一发送结果模型
- 发送异常
- 未来别的平台 sender

继续放一个文件里会越来越挤。

建议调整为：

- `app/services/im_sender/__init__.py`
- `app/services/im_sender/feishu.py`
- `app/services/im_sender/models.py`
- `app/services/im_sender/errors.py`

其中：

- `feishu.py`
  - 放 `FeishuMessageSender`
- `models.py`
  - 放 `SentMessageResult`
- `errors.py`
  - 放 `SendMessageError`

这样后续记忆写入只依赖统一发送结果模型，不需要知道底层是飞书 sender 还是别的平台 sender。

## 调用链建议

一期建议的调用链如下：

1. `gateway` 只做飞书事件归一化。
2. `router` 收到 `IncomingChatMessage` 后，先写入用户消息记忆。
3. `router` 调 `agent` 生成回复。
4. `router` 调 `services/im_sender/` 发送回复。
5. 发送成功后，`router` 再写入系统回复记忆。

这样可以先打通同步最小闭环，不额外引入异步复杂度。

## 后续演进但本次不做

这次方案先不扩展以下内容，只在接口层留演进空间：

- 记忆摘要沉淀
- 长期记忆筛选
- 基于向量检索的召回排序
- 独立消息表、发送记录表、事件日志表的完整实现
- 异步向量生成与补偿机制

后续如果消息量上来，建议把“写原文”和“算向量”拆成异步 worker，但一期先同步落库，链路最清晰。

## 建议新增的代码落点

如果后续你确认要开始实现，建议按下面的最小结构补代码：

- `app/memory/models.py`
  - 定义 `MemoryRecord` 等内部模型
- `app/memory/service.py`
  - 定义并实现 `ConversationMemoryService`
- `app/memory/embeddings.py`
  - 定义 `EmbeddingProvider` 与 `SentenceTransformerEmbeddingProvider`
- `app/memory/repositories.py`
  - 定义 `ConversationMemoryRepository`
- `app/memory/postgres_repository.py`
  - 放 PostgreSQL + `pgvector` 实现
- `app/bootstrap/app.py`
  - 放应用内部依赖装配
- `app/services/im_sender/`
  - 调整为目录结构，返回统一发送结果模型
- `app/event/models.py`
  - 给 `IncomingChatMessage` 补 `message_time`
- `app/router/session_manager.py`
  - 编排用户消息写入与系统消息写入
- `app/bootstrap/feishu.py`
  - 只保留飞书启动与接入相关逻辑
- `app/gateway/dispatch/feishu.py`
  - 放飞书 dispatcher

## 一期实现顺序建议

为了保持小步推进，正式编码时建议按下面顺序做：

1. 先补统一内部模型：`IncomingChatMessage.message_time` 与 `SentMessageResult`
2. 再定义 `MemoryRecord`、`EmbeddingProvider`、`ConversationMemoryRepository`
3. 再补 `ConversationMemoryService`
4. 再写 PostgreSQL 表与仓储实现
5. 最后把 `SessionManager` 和 `im_sender` 串起来

## 结论

这次“对话记忆”能力，一期最合适的做法是：

- 用一张 `chat_memory` 表先打通最小闭环。
- 用 `SentenceTransformer paraphrase-multilingual-MiniLM-L12-v2` 生成 `384` 维向量。
- 底层先落 PostgreSQL + `pgvector`。
- 主键使用 `GENERATED ALWAYS AS IDENTITY`。
- 一期默认加上 `hnsw` 向量索引。
- 上层通过 `ConversationMemoryService + EmbeddingProvider + ConversationMemoryRepository` 抽象调用，不感知底层实现。
- 收消息和发消息成功都在 `router` 编排层触发记忆写入，飞书原始时间如为毫秒值则先转换，再统一写入 `message_time`。

如果这份方案方向对，我下一步再按这个文档开始最小实现，不额外扩范围。
