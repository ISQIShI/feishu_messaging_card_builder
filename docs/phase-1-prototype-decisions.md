# Phase 1 Prototype Decisions

本文档冻结 Phase 1 最小原型阶段的所有关键设计决策。Phase 1 的目标是验证“Hermes 消息 → 飞书卡片实体 → 发送与更新”这一核心链路。

## Scope (范围)

- **Final Replies Only**: 仅处理 Hermes 的最终回复消息。不处理中间推理状态、流式输出、工具调用过程或后台日志。
- **One Card Per Final Reply**: 每条 Hermes 最终回复对应且仅对应一个飞书卡片实体。
- **Websocket-only**: 仅支持 Hermes 的 Feishu/Lark websocket 连接模式。
- **English/Chinese Support**: 支持中英文内容转换。

## Content Contract (内容契约)

- **Markdown to Card Component**: 将 Hermes 的 Markdown 文本块转换为飞书 Card JSON v2 的 `markdown` 组件。
- **Static Headers**: 原型阶段使用固定的卡片标题和副标题。
- **Schema Version**: 强制使用 Card JSON v2 ("2.0")。
- **Config**: 启用 `update_multi: true` 以允许卡片多次更新。

## Update Model (更新模型)

- **Full-card Replacement**: 更新时采取全量替换模式，不进行增量组件差异对比（diffing）。
- **Sequence-based Update**: 基于自增序列或时间戳确保更新顺序，避免旧版本覆盖新版本。

## Storage (存储)

- **SQLite via stdlib**: 使用 Python 标准库自带的 `sqlite3` 模块。
- **Primary Key**: 以 `bridge_message_id` 为主键，关联 `hermes_message_id`、`feishu_card_id`、`feishu_message_id` 和当前 `version`。

## Live Validation (实时验证)

- **Mock-first Validation**: 核心逻辑必须能通过 mock 飞书 API 进行验证。
- **Optional Live Evidence**: 实时发送到飞书作为可选证据，非强制性阻断测试。

## Out-of-scope Items (超出范围)

- **Webhook Support**: 不支持飞书 Webhook 模式。
- **Streaming Updates**: 不支持打字机式的流式更新。
- **Rich Media**: 不支持图片、音频、视频、表格、附件。
- **Card Actions**: 不支持卡片上的交互式按钮（Phase 1 仅关注展示与更新）。
- **Tool Payloads**: 不支持将 Hermes 的工具调用参数渲染为卡片。

## 关键限制

- **No Hermes Source Modification**: Phase 1 禁止修改任何 Hermes 源码。
- **Independent State**: 桥接层维护独立的状态库，不依赖 Hermes 的会话存储持久化。
