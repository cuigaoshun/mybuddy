# AGENTS.md

## OVERVIEW
- `app/bootstrap/` 只负责应用装配、生命周期和平台接入初始化，不承接业务策略。
- 这里的核心是把配置、基础设施、监听器和运行时对象按启动顺序接起来。
- 子目录内最重要的边界是，`application.py` 管启动，`container.py` 管依赖图，平台 helper 管接线，`listener.py` 管统一启停。

## STRUCTURE
- `application.py`，FastAPI lifespan 入口，负责 `load_dotenv()`、`init_config()`、provider override、预热重资源、启动监听器。
- `container.py`，`AppContainer` 定义处，集中声明 provider 关系、单例范围、工厂边界和跨模块依赖。
- `listener.py`，统一 listener 生命周期管理器，当前收口飞书 websocket 和微信长轮询 runner。
- `feishu.py`，装配飞书 client，订阅事件总线，启动和关闭 websocket listener。
- `wechat.py`，装配微信 polling runner，订阅事件总线并注入运行时依赖。
- `postgres.py`，只负责根据配置创建 SQLAlchemy `Engine`。
- `protocols.py`，定义启动辅助函数依赖的最小容器协议，不暴露整个容器实现。

## WHERE TO LOOK
- 看启动顺序和预热行为，先读 `application.py`。
- 看 provider 生命周期和对象归属，直接读 `container.py`。
- 看监听器怎么被统一托管，读 `listener.py`。
- 看平台初始化 helper 该拿哪些依赖，读 `protocols.py`，再对照 `feishu.py` 和 `wechat.py`。
- 看数据库 engine 如何进容器，读 `postgres.py`。

## CONVENTIONS
- `application.py` 拥有启动阶段的真实控制权，包含配置加载、容器实例化、provider override、模块 wiring、资源预热和 listener 启动。
- 启动预热目前明确包括 `engine()`、`embedding_provider()`、`agent_graph()`、`memory_graph()`，新增重资源时先判断是否应在这里预热。
- `container.py` 保持 wiring 导向，provider 命名直接对应业务对象或基础设施，不在这里夹带业务分支判断。
- 容器里单例和工厂的划分有明确意图，基础设施、图、service、sender 多为 `Singleton`，会话编排器和 dispatcher 用 `Factory`。
- 平台 bootstrap helper 只做接线，典型动作是校验容器依赖、订阅 `EventBus`、创建 client 或 runner，不吸收消息策略。
- `listener.py` 是统一 listener 入口，新的平台监听器要并入这里的生命周期，而不是各自散落在 `application.py`。
- `protocols.py` 维持最小接口面，helper 需要新依赖时先补协议，再补容器 provider，避免偷拿完整容器实现细节。

## ANTI-PATTERNS
- 不要把业务规则、路由判断或消息处理策略塞进 `bootstrap` helper；这里负责接线，不负责决策。
- 不要在 `application.py` 外重复做 provider override 或资源预热，启动顺序必须集中在 lifespan。
- 不要绕过 `listener.py` 直接起后台任务，否则关闭顺序、任务回收和 `app.state` 可观测性会分叉。
- 不要让 `protocols.py` 变成 `AppContainer` 的镜像，helper 用不到的 provider 不应加进去。
- 不要在 `postgres.py` 里扩展仓储或业务逻辑，它只负责 engine 创建。

## NOTES
- `application.py` 当前只启动 `container.listener().start(app)`，`memory_scheduler_runner().start(app)` 仍是注释状态，判断后台任务是否在线时要以这里为准。
- `listener.py` 会把自身挂到 `app.state.listener`，运行时排查 listener 状态先看应用状态对象。
- 飞书和微信入站最终都会订阅到统一的 `incoming_chat` topic，bootstrap 层只负责把平台入口接到统一事件总线。
- `configure_logging()` 目前在飞书 client 装配时触发，涉及平台日志初始化时先确认是否会影响全局日志行为。
