# Phase 3 Runtime Bridge Design Freeze & Harness

> 状态：Design Freeze & Harness Verification Complete
> 
> 范围：本文档冻结 Phase 3 运行时桥接层的设计边界、最小事件契约、状态与证据口径。当前仓库提供运行时桥接验证框架（Harness），用于在 mock 环境下验证契约，但不代表仓库现在已经提供生产环境的 live runtime bridge。

## Overview / TL;DR

Phase 3 的首要目标不是扩展更多飞书能力，而是把现有 Phase 1/Phase 2 已经验证或冻结的约束，收敛成一份 **可执行但暂不落地实现** 的运行时桥接设计备忘录。

本设计冻结以下结论：

- **首选接缝**：Hermes Feishu/Lark websocket 出站路径的 **external outbound observer/wrapper**，优先于源码补丁、Webhook 重定向或 repo-owned live transport。
- **事件契约**：运行时桥接层只消费一份最小化的规范化出站事件，核心字段固定为 `source_platform`、`session_key`、`hermes_message_id`、`final_reply_index`、`content_markdown`、recipient identifier、recipient type。
- **运行时范围**：仅处理 Hermes **最终回复**；每条逻辑最终回复只对应 **一张卡片**；走 **entity-first create/send/update**；不接流式片段、工具调用过程、卡片动作或组件级增量更新。
- **持久化模型**：复用现有 SQLite 中心状态模型；不新增队列、不新增独立数据库、不把桥接层扩展成服务网格。
- **失败上限**：遇到不能安全判定远端结果的场景，一律收敛为 `reconciliation_required`；**不允许** blind resend、auto-backfill、background sweeper。
- **证据与检查**：safe inspect 默认只输出脱敏状态摘要；原始载荷、原始 ID、token、完整错误体不进入默认输出或持久化最小集。
- **可逆边界**：任何离开本仓库边界的集成都必须可安装、可检查、可更新、可卸载、可恢复；若这些条件无法满足，Phase 3 必须停在设计冻结，不进入实现。

## Design Principles

### 1. Wrapper-first

Phase 3 冻结 **wrapper-first seam**：优先在 Hermes 进程外观察或包装 websocket 出站行为，而不是先假定 Hermes 源码补丁、运行时 monkey patch 或 webhook 接管。

这样做的原因：

- 与 `docs/hermes-outbound-seam-memo.md` 的首选接缝一致；
- 保持 Hermes 作为对话语义来源地；
- 最大化可逆性与审计性；
- 避免在 Gate B 前把实现承诺扩大成“只差部署”的运行时产品。

### 2. Reversible by default

桥接方案若需要改动 Hermes 配置、运行目录、启动方式或外围执行包装器，该改动必须先满足可逆集成边界：

- 可安装；
- 可检查当前状态；
- 可更新；
- 可卸载；
- 可恢复到安装前或明确定义的安全基线。

若做不到这一点，设计应停留在 memo 层，不得用“先实现再补回滚”替代。

### 3. Entity-first lifecycle

Phase 3 继续冻结飞书卡片的主路径为：

1. create card entity；
2. 获得 `card_id`；
3. 按 `card_id` send；
4. 在允许窗口内按 `card_id` update。

一次性 raw Card JSON 发送不是主路径，也不应在运行时桥接设计中被重新抬升为默认交付方式。

## Preferred Integration Seam

### External Websocket Outbound Observer/Wrapper

Phase 3 的首选接缝冻结为：**external websocket outbound observer/wrapper**。

定义：

- 它位于 Hermes 进程外或 Hermes 启动包装层外侧；
- 它观察 Hermes 面向 Feishu/Lark websocket 的出站最终回复事件；
- 它把这些出站事件规范化为桥接层可消费的最小契约；
- 在可安全控制的前提下，原始文本发送可被抑制或替换为卡片路径；
- 若无法安全抑制，允许在验证阶段保留受控 dual-delivery 作为证据工具，而不是产品默认行为。

冻结理由：

- 这是目前最符合“外部改动必须可逆”的路径；
- 它不要求在设计冻结阶段承诺 Hermes 源码补丁；
- 它把运行时桥接职责限制在“观察、规范化、投递、记账”四类责任内；
- 它避免把 webhook、HTTP 服务部署或 repo-owned transport 引入当前边界。

### Rejected as default seams

以下路径在 Phase 3 不得作为默认接缝：

- Hermes 源码补丁；
- Python decorator / monkey patch 注入；
- webhook redirection；
- 新增 repo-owned live transport service；
- 直接依赖日志扫尾或 DB sweeper 作为主路径。

## Normalized Outbound Event Contract

Phase 3 冻结运行时桥接层消费的最小规范化出站事件字段。任何实现都不得减少以下核心字段，也不应在 Gate B 前把契约扩展成宽泛的“全平台消息总线”。

### Required Fields

| Field | Required | Meaning |
|------|----------|---------|
| `source_platform` | Yes | 源平台标识。Phase 3 冻结为 Hermes Feishu/Lark websocket 上下文。 |
| `session_key` | Yes | Hermes 会话稳定键，用于区分会话边界与同一上下文下的最终回复归属。 |
| `hermes_message_id` | Yes | Hermes 逻辑消息身份，表示该最终回复来自哪条 Hermes 消息。 |
| `final_reply_index` | Yes | 同一 Hermes 消息下第几个最终回复；用于导出稳定逻辑身份。 |
| `content_markdown` | Yes | 要被卡片化的最终回复正文内容，使用规范化 Markdown 文本作为桥接层内容输入。 |
| recipient identifier | Yes | 接收方标识符，例如 open_id / union_id / chat_id 等单一受控标识；实现时必须与 recipient type 成对解释。 |
| recipient type | Yes | 接收方类型，例如 `user` / `chat` 等，用于选择 Feishu send path 所需的 receive_id_type。 |

### Frozen Derivation Rules

- `bridge_message_id` 的导出输入必须保持为：`source_platform + session_key + hermes_message_id + final_reply_index`。
- `idempotency_key` 在当前阶段可与 `bridge_message_id` 采用相同导出规则，但语义仍需保留为独立持久字段。
- `content_hash` 只从 `content_markdown` 派生；它用于内容变化检测，不用于绕过状态机。

### Contract Exclusions

本契约 **不** 把以下内容列为必需字段：

- 流式 chunk 序号；
- 工具调用明细；
- 模型推理过程；
- 原始 websocket 帧；
- 卡片按钮动作回调；
- 富媒体二进制内容；
- 多平台抽象字段。

这些内容若未来需要，应作为新阶段显式扩展，而不是偷偷塞进 Phase 3 的“最小出站事件”。

## Runtime Scope

### Frozen Scope

Phase 3 运行时范围冻结如下：

- **Final replies only**：只处理 Hermes 最终回复；
- **One card per logical final reply**：每个逻辑最终回复只对应一张飞书卡片实体；
- **Entity-first create/send/update**：先创建实体、再发送、后续再更新；
- **SQLite-backed state reuse**：沿用现有 SQLite 中心状态与身份语义；
- **No extra DB / No queue**：不新增消息队列、不新增独立数据库、不引入异步作业系统。

### Explicitly Out of Scope

以下内容在 Phase 3 明确排除：

- streaming token / chunk 级卡片更新；
- tool payload 渲染；
- background log message 卡片化；
- card action handling；
- component-level partial update；
- webhook delivery path；
- arbitrary multi-platform bridge abstraction。

### Behavioral Freeze

- 若同一逻辑最终回复后续内容变化，仍按现有生命周期契约决定 mutate pending 内容或 update 既有卡片；
- 不允许因为内容变化就创建重复卡片；
- 不允许把“一个最终回复”拆成多张卡片来规避状态管理复杂度。

## Identity and Persistence Model

Phase 3 冻结身份与持久化策略为 **SQLite reuse, not storage expansion**。

### Reused Persistent Model

桥接运行时应直接复用现有最小持久字段语义：

- `bridge_message_id`：逻辑最终回复身份；
- `idempotency_key`：投递幂等身份；
- `content_hash`：内容变化信号；
- `card_id`：飞书卡片实体身份；
- `version`：最后一次被远端接受的更新序列；
- `updatable_until`：本地可更新窗口截止时间；
- `status`：受 Phase 2 状态机约束的生命周期状态。

### Persistence Freeze

- 不新增第二套 bridge DB；
- 不新增 queue table 以外的调度系统语义；
- 不把“运行时观察事件”持久化成无限制原始日志仓；
- 不要求 background sweeper 负责状态纠偏。

### Why SQLite reuse is frozen

- Phase 2 已经冻结了最小可靠性状态模型；
- Phase 3 的目标是把 runtime bridge 接上这个模型，而不是重新设计数据平面；
- 多一套数据库或队列会扩大恢复、审计、迁移和卸载复杂度，与当前阶段不匹配。

## Failure Ceiling and Recovery

Phase 3 冻结一个保守且可审计的失败上限：**不能安全判定结果时，停止副作用扩张，收敛到 `reconciliation_required`。**

### Failure Ceiling

以下场景必须进入 `reconciliation_required` 或保持该终态：

- send 结果 ambiguous；
- update 结果 ambiguous；
- 远端成功但本地持久化失败；
- 无法可靠判断同一逻辑最终回复应复用哪条既有远端状态；
- 任何需要人工确认的跨边界不一致。

### Forbidden Recovery Behaviors

Phase 3 明确禁止以下“看起来自动恢复、实际扩大事故面”的行为：

- blind resend；
- automatic backfill；
- automatic sweep-and-fix；
- 在无确证前复用同一 `card_id` 重试发送；
- 在 ambiguous update 后假定远端未接受并继续推进 `version`；
- 通过补发第二张卡片掩盖 reconciliation gap。

### Allowed Recovery Posture

- 允许显式人工协调；
- 允许受控 inspect-state / audit / evidence 收集；
- 允许在明确属于 safe rejection class 时执行受契约约束的后续动作；
- 允许把 dual-delivery 仅作为验证或取证工具，而不是默认恢复机制。

## Safe Inspect and Evidence Rules

Phase 3 延续并收窄 Phase 2 的 safe inspect 与证据口径，确保运行时桥接不会因为排障需求而泄露原始载荷或环境敏感信息。

### Safe Inspect Defaults

默认 inspect / audit 输出只应包含：

- 生命周期状态；
- `bridge_message_id` 的安全替代表达或摘要；
- `content_hash`；
- `version`；
- `updatable_until`；
- 失败分类与精简错误码；
- 是否需要人工协调；
- 必要时间戳。

### Default Output Must Exclude

默认输出不得暴露：

- raw `content_markdown`；
- raw `card_id` / `message_id` / `receive_id` / `tenant_key`；
- token、authorization、secret；
- 完整错误响应体；
- troubleshoot URL；
- 原始 websocket frame 或长文本载荷。

### Evidence Rules

- “远端已接受”必须由受控日志、测试证据或审计产物证明；
- safe inspect 默认输出 **不能** 充当远端成功证明；
- 证据文件只记录最小设计审计结果，不记录 live credential 或原始交付内容；
- 若需要 debug/raw 模式，必须显式开关，并与默认安全模式清晰隔离。

## Reversible Integration Boundaries

Phase 3 冻结如下可逆集成边界：

1. 本仓库可以定义 wrapper / observer 的设计接口与证据口径；
2. 本仓库可以复用现有 SQLite 模型承接运行时状态；
3. 本仓库不得默认声称已经拥有 repo-owned live transport；
4. 任何 Hermes 外部包装、启动脚本、运行配置或部署层变更，都必须能审计并可回退；
5. 若某条接线方式无法做到可逆，就不能被写成默认集成路径。

这意味着：

- 可以设计“如何包裹 Hermes websocket 出站”；
- 不可以在 design freeze 中偷渡“必须修改 Hermes 某源码文件”；
- 可以为未来实现预留接缝；
- 不可以把不可恢复的环境改动伪装成“运维步骤”。

## Reversibility Specification & Check

为了确保项目的可逆性与最小侵入性，Plan 7 定义了以下可逆性规范：

1. **Harness-Level Proof Only**: Plan 7 仅通过 harness (测试马甲) 证明集成的可行性与可逆性，不引入生产级的 `install.sh`、`check.sh`、`update.sh` 或 `uninstall.sh` 脚本。
2. **Explicit Disable Mode**: 桥接层必须支持显式的禁用模式。通过 `--delivery-mode disabled` 标志，可以完全停用卡片转换逻辑。
3. **Zero-Operation Guarantee**: 在禁用模式下，系统必须满足以下证据口径：
   - `bridge_disabled: true`；
   - `native_delivery_recorded: true` (保持原始文本记录)；
   - 所有卡片操作计数器（`card_create_count`, `card_send_count`, `card_update_count`）均为 0。
4. **Forbidden Surfaces**: 仓库根目录严禁出现以下“硬侵入”文件或目录：
   - 文件：`install.sh`, `check.sh`, `update.sh`, `uninstall.sh`, `run.py.patch`；
   - 目录：`feishu_card_build/`。
5. **Escalation Path**: 若实现干净的拦截接缝必须修改 Hermes 源码，必须停止当前路径并创建 **Forced-Seam Decision Memo**，而不是直接应用补丁。

## Forced-Seam Escalation Triggers

只有在首选 wrapper-first seam 被证据证明不足以满足最小目标时，Phase 3 才允许进入 **forced-seam escalation** 讨论。以下触发条件冻结为 stop conditions；一旦命中，当前接缝不应继续模糊推进，而应停下并产出新的设计备忘录（Forced-Seam Decision Memo）。

### Trigger 1: Cannot observe stable final replies

若 external wrapper 无法稳定观察到 Hermes 最终回复边界，导致无法可靠导出 `source_platform + session_key + hermes_message_id + final_reply_index`，则触发升级讨论。

### Trigger 2: Cannot suppress or safely coexist with original text send

若 wrapper 无法抑制原始文本发送，且 dual-delivery 不能仅停留在受控验证阶段，而会成为常态产品行为，则触发升级讨论。

### Trigger 3: Preventing duplicate native text requires Hermes source patching

若要在生产环境防止飞书客户端同时显示原始文本和卡片（抑制原始文本），却发现外部 wrapper/observer 无法在不修改 Hermes 核心源码的前提下实现稳定抑制，则触发升级讨论。

### Trigger 4: Recipient identity cannot be extracted safely

若无法稳定获得 recipient identifier 与 recipient type，导致 send path 无法满足最小可审计投递条件，则触发升级讨论。

### Trigger 5: Wrapper path breaks reversibility

若为了实现 wrapper 必须引入不可安装、不可卸载、不可恢复、不可审计的 Hermes 或环境改动，则触发升级讨论。

### Trigger 6: Wrapper path cannot preserve failure ceiling

若 wrapper 实现会系统性地产生 ambiguous send/update，却又无法把结果安全收敛为 `reconciliation_required`，则触发升级讨论。

### Trigger 7: Required semantics demand internal Hermes seam

若最小目标所需的最终回复边界、接收者身份、发送抑制或状态同步语义，只有 Hermes 内部接缝才能提供，且已有书面证据证明外部 wrapper 不足，则触发升级讨论。

### Escalation Rule

一旦触发任一条件：

- 停止把 wrapper-first 继续当作“差一点就能上线”的默认实现；
- 不直接提交 Hermes patch；
- 必须停下并产出 **Forced-Seam Decision Memo**，说明为何首选接缝失效、为何新接缝更可逆、如何安装/审计/回滚。

## Non-Goals

本文档明确不是以下内容的授权，且实现阶段严禁偷渡相关逻辑：

- **Implementation Code**: 本阶段不产出任何运行时桥接层的生产代码。
- **Live Transport**: 仓库不拥有、不实现、不部署 live websocket/webhook transport 逻辑。
- **Hermes Patch**: 严禁在 Phase 3 阶段实现或应用 Hermes 源码补丁。
- **Webhook Path**: 不支持 Webhook 重定向或 Webhook 签名验证逻辑。
- **Streaming & Process Messages**: 不支持流式片段、工具调用过程、思考摘要或中间状态的卡片化。
- **Component-Level Updates**: 仅支持整卡更新，不支持组件级增量更新设计。
- **Card Actions**: 暂不包含卡片按钮、交互回调或交互回流处理。
- **Service Deployment**: 不包含容器化、服务化部署或运维管理系统。
- **Tool Payload Rendering**: 不包含对复杂工具调用载荷的特殊渲染逻辑。
- **Automated Reconcile**: 不包含自动 reconcile 命令或后台修复器。


## Implementation Status

当前状态为 **Design Freeze & Harness Verification Complete**。

- 桥接框架：已实现运行时桥接层（Runtime Bridge Harness）的 mock/offline 验证框架；
- 状态同步：支持在 mock 环境下模拟 Hermes 消息的双向交付与状态生命周期同步；
- 契约验证：通过独立的验证工具（harness）在不侵入 Hermes 源码的前提下完成了设计契约的验证与证据收集。

注意：本阶段依然**不产出**生产环境的 live transport 逻辑，也不包含对 Hermes 的补丁（Patch）。
- 本仓库目前仍不提供 repo-owned runtime websocket bridge；
- `--live-feishu` 的 placeholder 边界不因本文档而改变；
- 任何后续实现必须先证明：它符合 wrapper-first、reversible、entity-first、SQLite reuse 与 failure ceiling 这五个冻结轴线。

换言之：本文档的价值在于 **收窄实现自由度**，而不是宣告“Phase 3 已经实现”。
