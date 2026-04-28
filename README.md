# Feishu Messaging Card Builder

本仓库已完成第一阶段（Phase 1）原型开发。仓库现在包含核心 Python 软件包、完整的测试套件以及命令行工具，用于验证从 Hermes 消息到飞书卡片实体的转换与更新流程。

本项目的目标是：将 Hermes 面向飞书发送的消息转换为飞书卡片形态，并以飞书卡片实体为中心完成发送与更新。

一个已经确认的方向是：飞书卡片应采用“创建卡片实体，获得 `card_id`，再通过卡片 ID 发送、更新”的方式，而不是把卡片 JSON 作为一次性消息直接发送。

当前原型以 Hermes Feishu/Lark 的 websocket 模式、飞书卡片实体生命周期和可逆集成为前提。面向协作者与代码代理的详细工作规则见 `AGENTS.md`。

## 当前阶段

仓库已进入 Phase 1：最小原型实现阶段。当前代码实现了以下核心能力：

- 消息解析：识别并提取 Hermes 原始消息中的关键意图与状态；
- 卡片渲染：基于 Card JSON v2 模板将解析结果转换为卡片结构；
- 实体管理：通过飞书 API 创建并更新卡片实体，维护 `card_id` 生命周期；
- 边界验证：通过 49 个自动化测试用例验证了核心逻辑在各种边缘情况下的表现。

## 文档入口

- `docs/README.md`：文档索引与阅读顺序。
- `docs/phase-1-prototype-decisions.md`：Phase 1 原型架构决策记录。
- `docs/hermes-outbound-seam-memo.md`：Hermes 出站消息拦截点深度研究。
- `docs/phase-1-live-validation.md`：Phase 1 现场验证记录与证据。
- `docs/project-direction.md`：项目方向、目标、边界与设计原则。
- `docs/roadmap.md`：长期发展方向与阶段路线。

## 快速开始

### 运行测试
```bash
python -m pytest
```

### 使用 CLI
```bash
python -m feishu_messaging_card_builder.cli --help
```

## 权威资料


- Hermes 官方仓库：https://github.com/NousResearch/hermes-agent
- Hermes 官方文档：https://hermes-agent.nousresearch.com/docs/
- 飞书创建卡片实体：https://open.feishu.cn/document/cardkit-v1/card/create
- 飞书 Card JSON v2 结构：https://open.feishu.cn/document/feishu-cards/card-json-v2-structure
- 飞书 Card JSON v2 组件概览：https://open.feishu.cn/document/feishu-cards/card-json-v2-components/component-json-v2-overview

## 已包含内容

仓库目前包含：

- 可运行的 Python 软件包（位于 `src/`）；
- 核心逻辑的自动化测试用例（49 个测试通过）；
- 命令行验证工具（CLI）；
- Phase 1 架构决策与验证文档。

## 非当前内容

当前仓库暂不包含：

- 自动化的安装/卸载脚本（目前需手动安装依赖）；
- 生产环境的数据库持久化（目前使用内存状态）；
- 对 Hermes 源码的直接补丁应用（目前以拦截层形式存在）。
