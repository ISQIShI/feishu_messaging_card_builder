# Feishu Messaging Card Builder

本仓库已进入重构准备阶段。旧的补丁脚本、Python 实现、测试和迁移文档已经移除；当前仓库只保留项目目标说明、许可证、忽略规则，以及用于正式开发前决策的指导性文档。

本项目的目标是研究并最终实现一个工具：将 Hermes 面向飞书发送的消息转换为飞书卡片形态，并以飞书卡片实体为中心完成发送与更新。

一个已经提前确认的方向是：飞书卡片应采用“创建卡片实体，获得 `card_id`，再通过卡片 ID 发送、更新”的方式，而不是把卡片 JSON 作为一次性消息直接发送。

当前设计资料以 Hermes Feishu/Lark 的 websocket 模式、飞书卡片实体生命周期和可逆集成为前提。

## 当前阶段

当前阶段不是实现阶段，也不包含具体开发任务拆解。仓库中的文档用于回答这些问题：

- Hermes 官方能力边界是什么；
- 飞书卡片实体、Card JSON v2、发送与更新机制有什么约束；
- 未来项目应如何定义边界、非目标、风险和决策原则；
- 哪些问题必须在正式设计与编码前确认。

## 文档入口

- `docs/README.md`：文档索引与阅读顺序。
- `docs/project-direction.md`：项目方向、目标、边界与设计原则。
- `docs/hermes-research.md`：Hermes 官方资料研究摘要。
- `docs/feishu-card-research.md`：飞书卡片官方资料研究摘要。
- `docs/roadmap.md`：长期发展方向、阶段路线与决策检查点。
- `docs/git-standards.md`：分支、提交、PR 与历史整理规范。
- `docs/open-questions.md`：正式设计前必须确认的问题。

## 权威资料

- Hermes 官方仓库：https://github.com/NousResearch/hermes-agent
- Hermes 官方文档：https://hermes-agent.nousresearch.com/docs/
- 飞书创建卡片实体：https://open.feishu.cn/document/cardkit-v1/card/create
- 飞书 Card JSON v2 结构：https://open.feishu.cn/document/feishu-cards/card-json-v2-structure
- 飞书 Card JSON v2 组件概览：https://open.feishu.cn/document/feishu-cards/card-json-v2-components/component-json-v2-overview

## 非当前内容

当前仓库暂不包含：

- 可运行代码；
- 安装、更新、卸载脚本；
- 对 Hermes 源码的补丁；
- 测试用例；
- 具体技术栈选择；
- 短期任务排期。
