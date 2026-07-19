# AGENTS.md

仓库基线：`main` @ `49da3ea`

## OVERVIEW
- 项目是一个 Python 3.11 的聊天应用后端，HTTP 入口用 FastAPI。
- 依赖注入由 `dependency-injector` 驱动，应用总装配点是 `AppContainer`。
- 回复生成主链路基于 LangGraph。
- 存储主轴是 PostgreSQL，向量检索用 `pgvector`。
- 配置加载来自 Dynaconf，日志统一收口到 Loguru。
- Web 搜索能力当前接 Exa。
- 根级文件只管仓库总览。更深规则后续放在 `app/agent`、`app/storage`、`app/bootstrap`。

## STRUCTURE
- `app/main.py`，ASGI 入口，只做 `create_app()`。
- `app/bootstrap/`，应用装配、生命周期、外部 client、监听器、数据库 engine。
- `app/api/routes/`，HTTP 路由层，目前很薄。
- `app/router/`，统一聊天会话编排入口。
- `app/agent/`，上下文组装、工具注册、LangGraph 图定义与运行时。
- `app/storage/`，领域模型、仓储协议、PostgreSQL 实现、向量检索、记忆服务。
- `app/services/`，LLM client、IM sender、Web 搜索等外部能力封装。
- `app/gateway/`，第三方事件接入和归一化。
- `app/workers/`，轮询和后台扫描任务。
- `app/pkg/weixin/`，Python 侧微信协议包，供应用层复用。
- `docs/trigger/README.md`，仓库里少数明确写出边界约束的设计文档。
- `tests/`，更像脚本和演示，不是可依赖的成熟自动化测试套件。

## WHERE TO LOOK
- 看应用启动链，先读 `app/main.py`，再读 `app/bootstrap/application.py`，最后落到 `app/bootstrap/container.py`。
- 看依赖关系和单例生命周期，直接读 `AppContainer` provider 定义。
- 看统一聊天主流程，读 `app/router/session_manager.py`。
- 看 Agent 怎么取上下文、检索记忆、调工具，读 `app/agent/graph/main_graph/builder.py` 及其同目录节点。
- 看记忆写入、历史检索、向量召回，读 `app/storage/service.py` 和 `app/storage/postgres/`。
- 看配置键名和默认值，读 `app/core/config.py` 和根目录 `config.toml`。
- 看日志输出位置和格式，读 `app/core/log.py`。
- 看容器化启动方式，读 `Dockerfile` 和 `docker-compose.yml`。
- 看提醒能力该放哪，不要猜，先读 `docs/trigger/README.md`。

## CONVENTIONS
- 启动链固定是 `app/main.py` -> `app/bootstrap/application.py` -> `AppContainer`。
- `create_app()` 只建 FastAPI 实例和挂路由，真正初始化放在 lifespan。
- 配置先 `load_dotenv()`，再 `init_config()`，再 override 到容器依赖。
- 重资源在启动期预热，当前包括数据库 engine、embedding provider、agent graph、memory graph。
- `SessionManager` 是统一聊天编排入口，负责身份收敛、记忆写入、回复租约、发送回复、更新会话状态。
- `app/agent` 负责图、上下文、工具和模型调用编排，不负责底层存储实现。
- `app/storage` 负责协议、模型、仓储、检索、向量搜索和记忆相关服务。
- `app/bootstrap` 只负责 wiring 和 lifecycle，不放业务判断。
- 存储服务倾向先走 service/repository 抽象，再落 PostgreSQL 实现。
- 历史检索不是纯文本过滤，当前会走词法召回加向量召回合并。

## ANTI-PATTERNS
- 不要把长时间等待或提醒业务塞进 `router`、`gateway` 或 `bootstrap`。`docs/trigger/README.md` 已明确否定这种做法。
- 不要让业务层直接拼 SQL。先定义仓储接口，再放进 `app/storage/postgres/` 实现。
- 不要把 `bootstrap` 当成业务层。它的职责是装配、启动、停止。
- 不要把 `tests/` 当成强约束回归网，改动前后需要自己判断验证面。
- 不要绕过 `SessionManager` 再各处散落聊天主流程，否则身份映射、去重、租约和记忆状态会分叉。
- 不要在路由层堆业务逻辑，当前 `app/api/routes/` 有意保持很薄。

## UNIQUE STYLES
- 中文注释和中文 docstring 很常见，新增内容要跟现有文件语气一致。
- provider 命名直接贴业务对象名，容器里能看出单例、工厂、依赖覆盖关系。
- 业务边界偏明确，`agent`、`storage`、`bootstrap` 各自收口，不鼓励跨层偷拿实现细节。
- 图构建代码先组装 runtime context，再把节点函数包成闭包后挂进 `StateGraph`。
- 日志默认走 stderr 加 `logs/mybuddy.log` 双通道，格式由 Loguru 统一。

## COMMANDS
- 本地直接跑服务：`uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Docker 构建依赖：`uv sync --frozen --no-dev`
- 容器默认启动命令见 `Dockerfile`，对外端口映射见 `docker-compose.yml`，宿主机是 `18800:8000`。

## NOTES
- `app/api/routes` 不是主要复杂度来源，主要规则藏在 `bootstrap`、`router`、`agent`、`storage`。
- `app/agent`、`app/storage`、`app/bootstrap` 后续应各自补一份更细的目录级 AGENTS，不要把那些细则回填到根文件。
- `app/workers/memory_scheduler.py` 已经出现在容器里，但在 `application.py` 中暂时未启动，判断后台任务时要先看实际 wiring。
- `docker-compose.yml` 只挂了 `config.toml` 和 `logs/`，没有把源码目录整体挂进去。
