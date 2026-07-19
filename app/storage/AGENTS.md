# AGENTS.md

## OVERVIEW
- 这里仅说明 `app/storage` 子树的本地规则，默认你已经读过上层 `AGENTS.md`。
- 这一层负责领域模型、仓储协议、记忆与身份相关服务、PostgreSQL 落地实现，以及 embedding 抽象。
- 公开边界先看 `models.py` 和 `repositories.py`，它们定义了 storage 子树对外交换的数据形状与协议面。

## STRUCTURE
- `models.py`：共享领域模型，覆盖对话记忆、历史查询、会话租约、用户长期记忆、第三方身份、微信账号运行态。
- `repositories.py`：协议中心，定义 `ConversationMemoryRepository`、`ChatSessionInfoRepository`、`UserMemoryRepository`、`UserIdentityRepository`、`WeChatAccountRepository`。
- `service.py`：`ConversationMemoryService`，负责文本提取、向量生成、历史检索归一化、联合召回、结果合并、命中扩窗。
- `session_info_service.py`：会话元信息与回复租约控制。
- `user_memory_service.py`、`user_identity_service.py`、`wechat_account_service.py`：用户长期记忆、身份收敛、微信账号运行态编排。
- `postgres/`：各协议的 PostgreSQL 实现，使用 SQLAlchemy Core 和 `pgvector`。
- `embeddings/`：embedding 抽象与默认实现。

## WHERE TO LOOK
- 看共享数据边界，先读 `models.py`。
- 看仓储能力是否允许某个操作，读 `repositories.py`，不要先猜实现细节。
- 看记忆检索主流程，读 `service.py` 和 `postgres/conversation_repository.py`。
- 看回复租约与待处理会话，读 `session_info_service.py` 和 `postgres/session_info_repository.py`。
- 看长期记忆 JSON 结构与反序列化，读 `user_memory_service.py` 和 `postgres/user_memory_repository.py`。
- 看 embedding 行为，读 `embeddings/base.py` 与 `embeddings/sentence_transformer.py`。

## CONVENTIONS
- `models.py` 和 `repositories.py` 是稳定边界。新增存储能力时，先补领域模型或协议，再补具体实现。
- service 层不要求一律做薄封装。这里的 service 会归一化输入、组合多个查询步骤，并承接局部业务语义。
- PostgreSQL 实现必须留在 `app/storage/postgres/`，返回 `MemoryRecord`、`UserMemory`、`WeChatAccount` 这类领域模型，不要把 SQL row 或 `RowMapping` 往上层泄漏。
- 会话和消息时间统一转成 UTC。新增查询或写入时，沿用现有 normalize 辅助函数模式。
- 对话记忆写入先走 `ConversationMemoryService.store()`，由 service 提取文本并通过 `EmbeddingProvider` 生成向量。
- 历史检索不是纯文本过滤。当前实现会做全文检索加向量召回，再用 RRF 合并排序。
- 相似记忆命中后通常还要扩展上下文窗口。当前会按命中消息向前和向后各展开一条时间线消息。
- 某些仓储自己承载专门语义，不只是 CRUD。典型例子包括消息去重、回复租约竞争、待整理会话筛选、命中窗口展开。
- `EmbeddingProvider` 是唯一约定的 embedding 抽象。调用方只依赖 `embed_document()` 和 `embed_query()`。
- `SentenceTransformerEmbeddingProvider` 默认优先尝试仓库内 `model/baai`，其次才是传入路径或模型名；query 会自动补检索 instruction。

## ANTI-PATTERNS
- 不要在 storage 之外直接拼 storage 相关 SQL。
- 不要绕过协议类型直接依赖某个 PostgreSQL 类，除非你正在做容器 wiring 或底层实现替换。
- 不要把 service 当成无意义转发层。若已有归一化、合并、扩窗、身份绑定等逻辑，应继续放在 service，而不是散到调用方。
- 不要把历史检索改成单一路径后就宣称等价，词法召回、向量召回和排序合并是现有行为的一部分。
- 不要在仓储层返回裸 JSON 或未清洗字段，上层默认拿到的是已规范化的领域对象。

## NOTES
- `postgres/conversation_repository.py` 是本子树热点文件，改动前先确认是否影响去重、全文检索、向量召回、时间排序和窗口展开。
- `postgres/session_info_repository.py` 不只是会话读写，它还定义了回复租约竞争和待做长期记忆整理的筛选语义。
- `postgres/user_memory_repository.py` 负责 `user_profile_json` 和结构化 `UserMemoryProfile` 之间的转换，新增字段时要同时考虑序列化与反序列化。
- 现有 `tests/` 更像脚本集合，不足以兜住 storage 改动。涉及检索、排序、时间归一化或租约语义时，要主动做更细的验证。
