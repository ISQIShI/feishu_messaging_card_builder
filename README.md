# Feishu Messaging Card Builder

本仓库已完成第一阶段（Phase 1）原型开发与第二阶段（Phase 2）可靠性加固，并已实现第三阶段（Phase 3）运行时桥接的设计冻结与离线验证框架。仓库现在包含核心 Python 软件包、详尽的测试套件、命令行工具以及桥接验证马甲（Harness），用于验证从 Hermes 消息到飞书卡片实体的转换、更新与运行时契约。

本项目的目标是：将 Hermes 面向飞书发送的消息转换为飞书卡片形态，并以飞书卡片实体为中心完成发送与更新。

一个已经确认的方向是：飞书卡片应采用“创建卡片实体，获得 `card_id`，再通过卡片 ID 发送、更新”的方式，而不是把卡片 JSON 作为一次性消息直接发送。

当前原型以 Hermes Feishu/Lark 的 websocket 模式、飞书卡片实体生命周期和可逆集成为前提。面向协作者与代码代理的详细工作规则见 `AGENTS.md`。

## 当前阶段

仓库已完成 Phase 2 可靠性加固（Plan 5/6），并进入 Phase 3 运行时桥接（Plan 7）。当前代码实现了以下核心能力：

- 桥接验证：实现运行时桥接层（Runtime Bridge Harness）的离线验证框架，用于模拟 Hermes 最终回复的双向交付、身份导出与状态生命周期同步。
- 离线环境：验证工具在受控 mock 环境下运行，验证逻辑与契约正确性，**不包含** 生产环境的 live 传输层（Live Transport）或对 Hermes 的补丁（Patch）。
- 消息解析：识别并提取 Hermes 原始消息中的关键意图与状态；
- 卡片渲染：基于 Card JSON v2 模板将解析结果转换为卡片结构；
- 实体管理：通过飞书 API 创建并更新卡片实体，维护 `card_id` 生命周期；
- 边界验证：通过详尽的自动化测试用例验证了核心逻辑在各种边缘情况下的表现。

注意：本项目依然保持 websocket-only 范畴，不包含 Webhook 路径。

## 文档入口

- `docs/README.md`：文档索引与阅读顺序。
- `docs/phase-1-prototype-decisions.md`：Phase 1 原型架构决策记录。
- `docs/hermes-outbound-seam-memo.md`：Hermes 出站消息拦截点深度研究。
- `docs/phase-1-live-validation.md`：Phase 1 现场验证记录与证据。
- `docs/phase-3-runtime-bridge-design.md`：Phase 3 运行时桥接设计冻结备忘录与契约。
- `docs/evidence-privacy-taxonomy.md`：证据与隐私分类规范。
- `docs/project-direction.md`：项目方向、目标、边界与设计原则。
- `docs/roadmap.md`：长期发展方向与阶段路线。

## 快速开始

### 运行测试
```bash
.venv/bin/python -m pytest
```

### 使用 CLI
```bash
.venv/bin/python -m feishu_messaging_card_builder.cli --help
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
- 核心逻辑与运行时桥接的详尽自动化测试用例；
- 命令行验证工具与桥接验证马甲（Harness）；
- Phase 1/2/3 的架构决策、可靠性契约与验证文档。

## 非当前内容

当前仓库暂不包含：

- 自动化的安装/卸载脚本（目前需手动安装依赖）；
- 生产环境的数据库持久化（目前使用 SQLite 文件存储）；
- 对 Hermes 源码的直接补丁应用。
