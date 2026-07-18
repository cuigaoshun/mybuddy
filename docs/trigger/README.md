# Trigger 提醒能力设计

如果要支持“6 点提醒我点外卖”这类需求，最小闭环建议设计成一条单独的 trigger 链路，而不是把它塞进当前普通聊天回复流程里。

## 第一阶段目标

- 用户在飞书里表达提醒意图。
- Agent 判断这是一个可执行提醒，并调用 trigger 工具。
- trigger 工具只负责把结构化提醒写入存储，不直接承担定时等待。
- 后台扫描器按固定间隔检查所有到期 trigger。
- 到期后通过统一的 `services/im_sender` 给用户发提醒消息。

## 主链路

这条链路可以概括为：

1. 用户发送“6 点提醒我点外卖”这类消息。
2. `agent` 在当前工具调用链路里选择 trigger 工具，并提取提醒文本、触发时间、目标会话、目标用户等结构化字段。
3. trigger 工具通过 `memory` 层新增的仓储抽象保存 trigger 记录，当前实现仍可先落 PostgreSQL。
4. `workers` 层新增一个和 `memory_scheduler` 类似的定时扫描器，周期性读取“已到期、未触发”的 trigger。
5. 扫描器触发后调用 `services/im_sender` 发送提醒文案，并把 trigger 状态更新为已触发，必要时记录发送结果。

## 模块职责

按当前仓库边界，模块职责建议这样划分：

- `app/agent/`：负责识别提醒意图，并调用 trigger 工具。
- `app/agent/context/tools/`：新增 trigger 工具定义与注册入口。
- `app/memory/`：新增 trigger 领域模型、仓储抽象、查询接口和 PostgreSQL 实现。
- `app/workers/`：新增 trigger 扫描与触发执行逻辑。
- `app/services/im_sender/`：继续负责真正的飞书消息发送。
- `app/bootstrap/container.py` 与 `app/bootstrap/application.py`：负责把 trigger 相关 service、repository、scheduler runner 装配并启动。

需要明确的边界：

- `router` 仍然只负责“收到一条入站聊天消息后”的主流程编排，不负责长期挂起等待某个时间点。
- `gateway` 仍然只负责飞书事件接入与归一化，不负责提醒业务。
- `bootstrap` 只负责装配和启动，不承载 trigger 业务逻辑本身。

## 最小数据模型

如果按最小实现推进，trigger 数据至少需要这些字段：

- `trigger_id`
- `user_id`
- `im_type`
- `chat_id`
- `source_message_id`
- `trigger_text`，例如“点外卖”
- `scheduled_at`
- `status`，例如 pending / triggered / cancelled / failed
- `triggered_at`
- `created_at`
- `updated_at`

## 仓储抽象

在存储抽象上，不建议让业务层直接拼 SQL。更稳妥的做法是先定义独立 trigger 仓储接口，例如：

- 创建 trigger
- 查询到期 trigger
- 标记 trigger 已触发
- 取消 trigger
- 查询用户当前未完成 trigger

这样做和当前 `memory` 层的设计方向一致：先定义抽象，再补 PostgreSQL 实现。

## 一期约束

第一阶段建议只做最小提醒闭环，不主动扩展成通用任务系统：

- 先只支持单次提醒，不先做复杂重复规则。
- 先只支持 Agent 在聊天中登记提醒，不先做独立管理后台。
- 先只支持到点发一条文本提醒，不先做复杂补偿编排。
- 先沿用当前应用内 `APScheduler` 周期扫描模式，不把 `workers` 描述成已经完整落地的任务平台。

如果后续要正式实现，这个能力最适合作为“一期消息闭环上的扩展能力”推进，而不是把项目定位改成一个通用的定时任务系统。
