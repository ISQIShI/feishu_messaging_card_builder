# Hermes 官方资料研究摘要

## 资料范围

本摘要只依据 Hermes 官方仓库和官方文档，不依据本仓库旧实现。

- 官方仓库：https://github.com/NousResearch/hermes-agent
- 官方文档：https://hermes-agent.nousresearch.com/docs/
- Gateway internals：https://hermes-agent.nousresearch.com/docs/developer-guide/gateway-internals
- Agent loop：https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop
- Feishu/Lark 平台文档：https://hermes-agent.nousresearch.com/docs/user-guide/messaging/feishu
- Sessions：https://hermes-agent.nousresearch.com/docs/user-guide/sessions
- Session storage：https://hermes-agent.nousresearch.com/docs/developer-guide/session-storage
- Toolsets reference：https://hermes-agent.nousresearch.com/docs/reference/toolsets-reference

## 已验证事实

Hermes Agent 是一个多平台 agent 系统，官方文档覆盖消息网关、agent loop、会话、工具集和平台接入。它的 messaging gateway 是长期运行的服务，负责接入不同平台、归一化平台事件、维护聊天会话，并把消息分发给 `AIAgent`。相关资料见 Gateway internals 与 Agent loop 文档。

Hermes 内部使用接近 OpenAI 风格的消息结构，例如 `role`、`content`、`tool_calls` 等概念。对本项目而言，这意味着“Hermes 输出”不只是最终文本，还可能包含工具调用、命令、附件和会话上下文。

Feishu/Lark 是 Hermes 官方支持的平台。官方文档说明 Feishu 支持 `websocket` 和 `webhook` 两种连接方式，其中 websocket 是推荐方式；webhook 模式会暴露 `/feishu/webhook` 并依赖 `aiohttp`。本项目当前只把 websocket 作为设计范围，webhook 仅作为官方能力背景记录。

Hermes 的 Feishu 行为包括：私聊默认响应所有消息；群聊只在机器人被 @ 提及时响应；群聊会话可通过 `group_sessions_per_user` 保持按用户隔离。该行为会影响卡片状态应该按“用户 + 会话 + 消息”还是按“群聊共享消息”建模。

Hermes Feishu 文档说明其支持文本、图片、音频和文件附件。文档还提到 outbound markdown 会被渲染为飞书 post 消息，并在 post payload 被拒绝时回退为普通文本。这个能力说明 Hermes 已经有平台发送适配，但它不是通用的卡片实体生命周期抽象。

Hermes 官方支持飞书交互式卡片动作。文档要求订阅 `card.action.trigger`，启用 Interactive Card 能力；在 webhook 模式下还需要配置 Message Card Request URL。按钮点击会被转换为合成的 `/card ...` 命令事件，携带 JSON payload，并在一段时间内去重。Hermes 将这些卡片动作纳入普通命令处理流程。

Hermes 还使用交互式卡片承载审批流，例如 Allow Once、Session、Always、Deny。这说明卡片按钮在 Hermes 中是已知交互形式，但该事实不等于 Hermes 提供了通用的“任意 agent 回复转飞书卡片实体并持续更新”的能力。

Hermes 的会话存储是 source-aware 的，会记录平台、用户、完整消息历史和工具调用。对本项目而言，这意味着卡片状态可以参考 Hermes 会话语义，但不能简单假设 Hermes 会话 ID 就是飞书卡片 ID。

## 对本项目的含义

Hermes 更适合提供“消息来源、上下文、命令事件、平台用户与会话信息”。飞书卡片实体的创建、发送、更新、`card_id` 维护和失败补偿，更可能是本项目需要定义的桥接层职责。

未来设计不应只问“在哪个函数里替换发送文本”，而应先问：Hermes 的哪类消息应被转换为卡片、哪些消息仍应保留原平台行为、卡片状态如何与 Hermes 会话状态关联、卡片交互如何回流到 Hermes 命令体系。

由于当前范围限定为 websocket，未来方案应优先研究 Hermes websocket 模式下的事件接收、重连、会话定位和发送路径。webhook 相关的 request URL、HTTP 服务部署和 webhook 签名处理不应进入首期架构。

## 不确定点

- Hermes 官方文档没有描述通用 outbound card entity 生命周期。
- Hermes 文档没有明确说明普通 agent 回复如何映射到可更新 `card_id`。
- Hermes 文档没有规定卡片更新失败后应如何回退到文本或新卡片。
- Hermes 的 Feishu 卡片动作能力偏向交互事件处理，不等同于卡片实体管理能力。
- websocket 模式下，项目如何最小侵入地接入 Hermes 出站消息仍需正式设计确认。

这些不确定点应在正式设计阶段被显式处理，而不是由代码隐式决定。
