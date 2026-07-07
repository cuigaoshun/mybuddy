# mybuddy

`mybuddy` 是一个陪伴型 Agent 项目，目标不是做一个一次性的聊天 Demo，而是先把“接收消息 → 理解上下文 → 读取记忆 → 生成回复 → 回写消息”这条链路打通，并把后续可持续演进的边界提前定清楚。

当前一期只围绕飞书展开：通过飞书 `websocket` 接收消息，通过飞书开放平台 API 发送消息，在中间接入 Agent 编排、记忆检索和 PostgreSQL 存储抽象，形成一个最小可运行闭环。

## 这个项目当前在做什么

当前仓库已经不是纯文档骨架，而是已经落下了一条一期主链路：

1. `app/bootstrap/application.py` 创建 FastAPI 应用，并在生命周期里初始化配置、数据库、向量模型和 Agent Graph。
2. `app/bootstrap/feishu.py` 装配飞书 `websocket` client，把飞书入站消息订阅到内部事件总线。
3. `app/gateway/dispatch/feishu.py` 把飞书事件转换成统一的 `IncomingChatMessage`。
4. `app/router/session_manager.py` 负责一条消息的主流程编排：用户消息入库、会话租约控制、调用 Agent、发送回复、助手消息回写。
5. `app/agent/` 负责构建对话上下文和 LangGraph 回复流程。
6. `app/memory/` 负责记忆写入、向量化、历史查询和 PostgreSQL 仓储实现。
7. `app/services/im_sender/feishu.py` 负责统一的飞书发送封装，不把飞书 SDK 直接暴露给上层。

换句话说，这个项目当前在做的是：先把“陪伴型 Agent 的最小消息闭环”做扎实，而不是同时铺开多平台、多后台或大而全能力。

## 一期范围

第一期明确只做这些事情：

- 只接入飞书，不扩展到企业微信、钉钉、Telegram、Slack 等其他平台。
- 用飞书 `websocket` 长连接接收消息事件。
- 用飞书 API 发送文本消息。
- 把平台事件尽早转换成项目内部统一消息模型。
- 通过 Agent、上下文构建、记忆检索生成回复。
- 使用 PostgreSQL 承担当前存储实现，但业务层只依赖抽象接口。

第一期明确不做：

- 多平台接入统一网关。
- 管理后台、运营后台、多租户控制台。
- 复杂权限系统。
- 过早拆分微服务。

## 当前链路

目前已经成形的核心链路可以概括为：

1. 飞书用户消息通过 `websocket` 进入系统。
2. `gateway` 层把飞书原始事件归一化成内部消息模型。
3. `event` 层把入站消息发布到内部事件总线。
4. `router` 层接住消息，执行去重、会话租约、记忆写入、回复编排。
5. `agent` 层基于上下文与记忆生成回复内容。
6. `services/im_sender` 调飞书 API 发送消息。
7. 用户消息、助手消息、会话信息等数据通过 `memory` 抽象落到 PostgreSQL。

当前 `app/agent/graph/` 里的工具调用链路已经收敛成两段：

- 核心工具直接作为常驻工具绑定给模型，并通过 LangGraph 原生 `ToolNode` 执行。
- 非核心工具先通过 `select_tool_category` 做工具大类选择，再只绑定该类别下的工具，由轻量动态工具节点执行。

也就是说，当前图里已经不再维护旧的 `ToolExecutor + ToolDefinition.execute + tool_expansion + context_update` 这套手写工具执行链，也不再把工具结果额外手工拼回提示词里；后续轮次主要依赖标准 `ToolMessage` 继续驱动模型。

## 当前目录职责

当前仓库里与一期主链路最相关的目录职责如下：

- `app/bootstrap/`：应用启动、依赖装配、飞书监听器启动。
- `app/api/routes/`：当前只包含基础 HTTP 路由，例如健康检查。
- `app/gateway/`：外部平台事件接入与归一化，目前重点是飞书消息分发。
- `app/event/`：内部事件模型与事件总线。
- `app/router/`：消息路由、会话处理、调用编排。
- `app/agent/`：上下文构建、工具选择、LangGraph 回复流程。
- `app/memory/`：记忆模型、仓储抽象、PG 仓储实现、向量检索与历史检索。
- `app/services/`：基础服务封装，目前包括 LLM 与统一 IM 发送。
- `app/workers/`：预留给异步任务；当前还没有完整落地后台消费逻辑。

仓库里还可以看到一些现状信号：

- `app/main.py` 是 FastAPI 入口。
- `app/api/routes/health.py` 提供了最小健康检查路由。
- `app/workers/consumer.py` 目前还是空文件，说明后台任务层还是预留状态。

## 飞书接入方式

当前飞书接入方向已经比较明确：

- 收消息参考 `tests/lark_on_bot.py`，以飞书 `websocket` 模式为主。
- 发消息参考 `tests/lark_u_to_bot.py`，通过飞书 SDK 调用发送接口。
- 正式代码里，飞书收消息逻辑收敛在 `app/bootstrap/feishu.py` 和 `app/gateway/dispatch/feishu.py`。
- 正式代码里，飞书发消息逻辑收敛在 `app/services/im_sender/feishu.py`。

这意味着后续开发需要继续坚持一个原则：飞书 SDK 调用不要散落到各处业务模块，平台字段要尽早收敛成内部统一模型。

## Agent、记忆与 RAG 的位置

当前项目里，这几个核心能力的边界已经基本清楚：

- Agent 放在 `app/agent/`，负责对话上下文构建、图编排和回复生成。
- 记忆放在 `app/memory/`，负责记忆写入、历史查询、向量召回和结果组织。
- RAG 在一期里不单独做复杂系统，而是作为记忆检索能力的一部分，先服务于对话上下文拼装。
- Router 不负责“思考”，而是负责把消息送到正确的会话与 Agent 流程里。

一期重点不是把 RAG 做复杂，而是先保证记忆读写、检索入口和回复链路真的能用。

## 当前工具调用方式

当前工具层的组织方式已经比较明确：

- `app/agent/context/tools/registry.py` 负责注册全部工具，并按“核心工具 / 工具大类”提供查询入口。
- `app/agent/context/tools/web_search_tools/search_web.py` 这类核心工具可以直接绑定给模型，并走 LangGraph 原生 `ToolNode` 执行。
- `app/agent/context/tools/history_tools/search_history.py` 这类非核心工具先不直接全量暴露，而是通过 `select_tool_category` 做渐进式披露。
- `app/agent/graph/nodes/tool_selector.py` 负责判断当前轮是直接回复、直接命中核心工具，还是先选择非核心工具大类。
- `app/agent/graph/nodes/tool_executor.py` 现在只保留一层非常薄的动态执行逻辑，用于执行当前已解锁类别下的非核心工具。

这套设计的目标不是做一个通用工具平台，而是先把飞书陪伴型 Agent 当前最需要的“核心工具直达 + 非核心工具按需解锁”做简单、稳定、可维护。

## 存储为什么要先抽象

虽然当前实现先使用 PostgreSQL，但代码设计上仍然要求上层只依赖抽象，而不是直接依赖 PG 细节。

当前仓库已经体现出这个方向：

- `app/memory/repositories.py` 定义了记忆仓储与会话信息仓储协议。
- `app/memory/postgres_repository.py` 提供对话记忆的 PostgreSQL 实现。
- `app/memory/postgres_session_info_repository.py` 提供会话信息的 PostgreSQL 实现。

这样做的原因很简单：陪伴型 Agent 的长期演进里，存储方案很可能变化。消息历史、长期记忆、向量检索、发送记录未来都可能拆开演化；如果业务逻辑一开始就写死在 SQL 和 PG 结构上，后面会非常难改。

## 当前已使用的 PostgreSQL 设计

当前最小记忆实现围绕以下对象展开：

- 记忆表：`chat_memory`
- 会话信息表：`chat_session_info`
- 消息内容：`content JSONB`
- 向量字段：`content_vector`
- 记忆检索：同时支持最近消息、全文检索、向量检索、按时间范围查询

初始化脚本位于：

- `scripts/init_chat_memory.sql`
- `scripts/migrate_chat_memory_userid_to_user_id.sql`

当前代码默认使用 `public.chat_memory` 等表结构，数据库初始化通过手动执行 SQL 脚本完成，代码本身不负责自动建表。

## 本地运行

应用入口是：

- `app/main.py`

本地开发常见启动方式：

- `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`

如果使用容器：

- `docker build -t mybuddy .`
- `docker compose up`

当前 `docker-compose.yml` 的思路是提供运行环境，并把本地代码挂载到容器里运行，而不是把业务代码直接打进镜像。

## 架构方案文档

当前仓库除了根 README 之外，还额外维护了一份针对 Agent 图重构的详细方案文档：

- `docs/architecture/README.md`

这份文档用于说明下一步要把 `app/agent/graph/` 重写成什么结构，重点覆盖：

- 新的图主流程如何从 `load_memory` 走到 `tool loop`
- 哪些能力第一阶段先做，哪些节点先占位
- 当前实现与目标图之间的差异

根 README 继续负责项目总览与当前状态；更细的图重构方案请看 `docs/architecture/README.md`。

## 参考文件

如果要继续理解或扩展一期主链路，优先看这些文件：

- `app/bootstrap/application.py`
- `app/bootstrap/container.py`
- `app/bootstrap/feishu.py`
- `app/gateway/dispatch/feishu.py`
- `app/router/session_manager.py`
- `app/memory/repositories.py`
- `app/memory/postgres_repository.py`
- `app/services/im_sender/feishu.py`
- `tests/lark_on_bot.py`
- `tests/lark_u_to_bot.py`
