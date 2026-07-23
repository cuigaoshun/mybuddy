# MyBuddy

MyBuddy 是一个基于 Python 3.11 的聊天应用后端，面向飞书和微信聊天场景。它的目标不是提供一个前端工作台，而是把聊天消息接入、上下文理解、LLM 回复、历史记忆和外部搜索串成一条可运行的后端链路。

如果你希望做一个能在企业 IM 或个人聊天场景中工作的智能助手后端，这个项目适合拿来做原型、内部工具接入、聊天助手能力验证，以及多平台消息统一编排的基础服务。

## 这个项目能做什么

当前仓库里已经能确认的能力包括：

- 统一聊天消息编排，作为聊天入口处理来自不同 IM 平台的消息
- 基于 LLM 的回复生成
- 历史消息检索，包括文本检索和向量召回
- 长期记忆处理，用于沉淀用户画像和长期上下文
- 网页搜索能力，当前接入 Exa
- 微信扫码登录与消息轮询
- 飞书接入与消息处理

## 适合什么场景

- 为飞书机器人或聊天助手提供后端能力
- 为微信侧接入一个可持续轮询和回复的聊天助手
- 需要把聊天上下文、历史记忆和网页搜索结合起来的问答场景
- 想验证多平台聊天助手的最小可用闭环

## 当前集成平台

- 飞书
- 微信

项目本身是后端服务，不提供现成的前端界面或管理后台。

## 运行依赖

启动前至少需要准备这些依赖：

- Python 3.11
- PostgreSQL
- 可用的 LLM API Key
- 可选的 Exa API Key，用于网页搜索

本地建议使用 `uv` 管理依赖。

## 配置说明

项目默认读取根目录 `config.toml`，并允许使用 `MYBUDDY_` 前缀环境变量覆盖配置。

当前 `config.toml` 中实际存在的配置分组如下。

### `app`

- `env`：运行环境，当前可用值为 `dev` 或 `prod`

### `feishu`

- `app_id`：飞书应用 ID
- `app_secret`：飞书应用密钥
- `log_level`：飞书相关日志级别

### `postgres`

- `port`：PostgreSQL 端口
- `user`：数据库用户名
- `database`：数据库名
- `schema`：数据库 schema
- `connect_timeout_seconds`：连接超时时间，单位秒

说明：代码中还支持 `postgres.host` 和 `postgres.password`，未写入当前示例文件时会使用默认值或空值。实际运行前请按你的数据库环境补齐。

### `llm`

- `model`：模型名
- `api_key`：LLM API Key
- `base_url`：模型服务地址，留空时按接入方默认行为处理
- `temperature`：采样温度

### `exa`

- `api_key`：Exa API Key
- `default_limit`：默认搜索条数

如果你不需要网页搜索能力，可以先不填写 `exa.api_key`。

## 本地运行

1. 安装依赖：

```bash
uv sync
```

2. 按实际环境修改根目录 `config.toml`，至少补齐：

- 飞书 `app_id`、`app_secret`
- PostgreSQL 连接信息
- `llm.api_key`

3. 确保 PostgreSQL 可用后，启动服务：

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

服务默认监听 `8000` 端口。

## Docker 运行

项目提供了 `Dockerfile` 和 `docker-compose.yml`。

1. 先基于 `Dockerfile` 构建镜像：

```bash
docker build -t mybuddy .
```

2. 再启动容器：

```bash
docker compose up
```

当前 `docker-compose.yml` 中的端口映射为宿主机 `18800:8000`。

容器方式会挂载：

- `./config.toml` 到容器内 `/workspace/config.toml`
- `./logs` 到容器内 `/workspace/logs`

因此，启动前同样需要先准备好本地 `config.toml`。

## 规划中的方向

定时提醒能力仍处于规划阶段，详细方案见 `docs/trigger/README.md`。

这部分目前应视为规划或后续方向，不应当理解为已经完成并默认可用的正式特性。

## 当前限制与注意事项

- 这是后端项目，默认重点在聊天链路，不是开箱即用的完整产品界面
- 运行依赖外部服务较多，至少包括数据库和 LLM 接口
- 网页搜索依赖 Exa，未配置 Key 时相关能力不可用
- 仓库中的 `tests/` 更接近脚本和演示，不适合当作成熟自动化测试套件来理解
- 提醒类 trigger 能力目前还是设计文档，不应按已上线能力使用

## 快速判断

如果你要找的是一个面向飞书和微信聊天场景的 Python 后端，并且希望它具备 LLM 回复、记忆检索、长期记忆和网页搜索能力，这个项目已经覆盖了核心骨架。

如果你要找的是一个包含完整前端、管理后台、成熟运维体系和现成提醒系统的产品，这个仓库当前还不是那个形态。
