# 重构准备文档索引

这些文档用于指导“正式开发前”的方向判断。它们不是实施计划，也不要求当前阶段选定所有技术细节。

建议阅读顺序：

1. `project-direction.md`：先理解项目未来要解决的问题、边界和原则。
2. `hermes-research.md`：再理解 Hermes 官方能力与它没有覆盖的部分。
3. `feishu-card-research.md`：确认飞书卡片实体、Card JSON v2、发送和更新约束。
4. `roadmap.md`：确认长期方向、阶段路线和哪些决策可以延后。
5. `git-standards.md`：确认分支、提交、PR 和历史整理规范。
6. `open-questions.md`：最后整理正式设计前必须确认的问题。

核心结论：未来方案应以飞书卡片实体为中心，维护 `card_id` 生命周期；Hermes 侧更可能提供消息、会话、平台事件和命令处理上下文，而不是直接提供通用的“可更新卡片实体”抽象。

当前约束：只考虑 Hermes Feishu/Lark websocket 连接方式；任何对 Hermes 源码或其他非本项目内容的修改，都必须可安装、可卸载、可更新、可审计和可恢复。
