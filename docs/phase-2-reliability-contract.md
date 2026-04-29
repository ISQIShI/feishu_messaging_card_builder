# Phase 2 Reliability Contract

本文档冻结 Plan 3 在代码变更前必须遵守的最小可靠性契约。它只解决本计划已经明确决定的状态、身份、幂等、更新窗口、失败分类和恢复边界；未在此处明确冻结的内容，仍应视为开放问题而不是隐含承诺。

> 范围说明：本文档只约束 SQLite 中心的最小状态模型、发送/更新决策和证据口径。Plan 3 的契约审计、测试与脚本命令统一使用 `.venv/bin/python`，但这不是新的运行时传输路径。

## 1. State Machine Table

下表定义 Plan 3 允许出现的全部状态、显式转移、触发原因与操作员动作。任何实现都不应扩展出未记录的隐式状态机。

| Status | Transitions To | Trigger | Resend Allowed | Update Allowed | Operator Action |
|--------|---------------|---------|---------------|----------------|-----------------|
| new | card_created, unsupported | get_or_create / unsupported content | N/A | N/A | none |
| card_created | send_pending, send_failed, reconciliation_required | send attempt / send error / persistence fail | Yes (same card_id) | No | retry process-fixture |
| send_pending | sent, send_failed, reconciliation_required | send success / send rejection / ambiguous | Yes (same card_id if explicit pre-acceptance rejection) | No | retry process-fixture or manual |
| send_failed | sent, reconciliation_required | retry with explicit rejection class / ambiguous | Only if explicit pre-acceptance rejection | No | manual decision |
| sent | updated, update_failed, expired | update attempt / update error / expiry | No (card_id already consumed) | Yes | update-card |
| updated | updated (higher version) | another update | No | Yes | update-card |
| update_failed | updated, reconciliation_required, expired | retry update / ambiguous / expiry | No | If unexpired | update-card |
| reconciliation_required | (terminal) | N/A | No | No | manual intervention |
| unsupported | (terminal) | N/A | No | No | fix content |
| expired | (terminal) | N/A | No | No | new card required |

补充约束：

- `send_pending` 不是装饰性状态，而是显式记录“已发起发送但尚未安全落盘为远端已接受”的中间态。
- `reconciliation_required` 是 Plan 3 的恢复上限：只要求状态可见、原因可查、操作员可介入，不在本计划中承诺额外自动恢复命令。
- `expired` 由本地可更新窗口判定触发，用于阻止过期后的静默更新。

## 2. Identity Semantics

Plan 3 将三类身份字段分开定义，避免把“逻辑消息身份”“幂等投递身份”和“内容变化信号”混成一个概念。

- `bridge_message_id`：稳定的 Hermes 逻辑回复身份。其导出必须是确定性的，输入为 `source_platform + session_key + hermes_message_id + final_reply_index`。
- `idempotency_key`：新的第一类持久化字段。初始阶段与 `bridge_message_id` 使用相同导出规则，但语义上单独保留，为后续需要拆分逻辑身份与投递身份时留下兼容空间。
- `content_hash`：`content_markdown` 的 SHA-256 哈希，用于检测同一逻辑身份下的内容是否变化。

补充约束：

- 同一条记录的 `bridge_message_id` 必须先表达“这是哪条 Hermes 最终回复”，再考虑其发送或更新命运。
- `idempotency_key` 作为持久字段必须可审计、可迁移、可从旧行派生，而不是运行时临时值。
- `content_hash` 只回答“内容是否变化”，不直接决定是否允许重发或更新；真正决策由状态机和过期窗口共同裁定。

## 3. Changed-Content Policy

Plan 3 冻结以下 changed-content 规则：

- Same `bridge_message_id` + same `content_hash` → idempotent replay，直接返回现有记录。
- Same `bridge_message_id` + different `content_hash` → 依据当前状态决定：
  - If status < sent：更新待发送记录中的内容，然后继续当前发送路径。
  - If status = sent AND unexpired：把它视为同一张卡片的更新，而不是静默创建重复卡片。
  - If expired/ambiguous：返回 `reconciliation_required`。
- 在 `get_or_create` 上遇到 content hash mismatch 时，抛出 `BridgeStateError`，由上层根据当前状态将其映射到“更新待发送记录”“更新已发送卡片”或“进入人工协调”。

补充约束：

- “ambiguous” 在此处指不能安全断定远端是否已接受发送/更新的状态，不能把它自动乐观地解释成可继续复用同一 `card_id`。
- changed-content 规则的目标是防止无声重复卡片，不是扩展为任意内容版本分叉系统。

## 4. Migration Policy

Plan 3 只接受对现有 Phase 1 / Plan 2 SQLite 行的原地升级，不接受丢数式重建。

- 迁移策略：对已有 SQLite 表执行 `ALTER TABLE ADD COLUMN`，逐步补齐新列。
- 新列的派生默认值：
  - `idempotency_key` ← `bridge_message_id`
  - `updatable_until` ← `created_at + 14 days`
  - `version` ← 由现有记录序列语义派生
- 老数据不得丢失；既有行必须保留，并以派生默认值进入新契约。
- 迁移目标是最小可靠性升级，不引入额外迁移框架，也不借机改变存储后端。

补充约束：

- 对旧行的默认值推导必须是可解释的；如果无法可靠推导，就应让该行落入可见的恢复路径，而不是静默伪造“已安全更新”。
- 本文档冻结的是迁移方向和默认值来源，不扩大到更宽泛的历史重写策略。

## 5. Update Window

Plan 3 把可更新窗口冻结为持久字段 `updatable_until`。

- `updatable_until` = `created_at + 14 days`。
- 该 14 天窗口来自官方文档口径，因此在本仓库中标记为 **doc-backed, not live-proven**。
- 一旦超过 `updatable_until`，记录状态应转为 `expired`，后续不再允许继续更新。

补充约束：

- 过期后不尝试“最好试一下也许还能成功”的更新；Plan 3 要求状态先收敛为 `expired`。
- 该窗口是针对“是否还允许对既有卡片继续更新”的本地契约，不等价于新的发送窗口。

## 6. Version Semantics

Plan 3 将 `version` 冻结为“last remotely accepted” 的 Feishu 更新序列定义。

- `version` = last remotely accepted Feishu update sequence。
- 失败更新不会推进 `version`。
- 成功更新后，才递增并持久化新的 `version`。
- `version` 直接作为 Feishu 更新请求中的 `sequence` 参数。

补充约束：

- `version` 不是“本地尝试次数”，也不是“最后一次看到的任意序号”；它只记录最后一次被远端接受的序列。
- 这一定义直接约束 stale sequence 的处理：如果远端没有接受，本地就不能推进序号。

## 7. Send Failure Classes

发送失败只分为三类，且每类都绑定最小恢复动作：

1. **Explicit pre-acceptance rejection**：Feishu 在消息被接受前就明确拒绝请求，例如 `invalid receive_id` 或其他清晰的接收方/校验错误。只有这一类才允许复用同一 `card_id` 重试发送。
2. **Ambiguous failure**：超时、5xx、网络中断、或其他无法判断远端是否已接受的错误。对此同一 `card_id` 绝不能盲目重发，必须进入 `reconciliation_required`。
3. **Local persistence failure after remote success**：远端已接受，但本地状态落盘失败。该情况同样进入 `reconciliation_required`，并要求给出恢复说明。

补充约束：

- “允许同卡重试”不是广义重试开关，只适用于已经被明确证明属于 pre-acceptance rejection 的发送错误。
- Plan 3 的 live validation 只要求收窄到 `invalid receive_id` 这类显式拒绝边界，不把更宽泛的远端错误一并视为安全可重试。

## 8. Update Failure Classes

更新失败分类独立于发送失败分类，Plan 3 仅冻结以下三类：

1. **Feishu API error**：进入 `update_failed`，`version` 保持不变；如果尚未过期，可以重试更新。
2. **Stale sequence**：进入 `update_failed`，并保留特定错误码 `300317` 语义，表示提交的 `sequence` 已落后。
3. **Expired card**：进入 `expired`，属于终态。

补充约束：

- 模糊更新失败同样不能推进 `version`；如果无法判断远端是否已接受更新，应转入 `reconciliation_required` 而不是伪装成普通 `update_failed` 成功可重试。
- `expired` 在更新路径中优先表示“本地契约已不允许继续更新”，不再尝试新序号补发。

## 9. Restart-Safe Updates

Plan 3 要求更新逻辑在进程重启后仍然可重建，而不是依赖内存缓存。

- `update_card` 必须从持久化状态重建更新 payload，至少依赖 `content_markdown` 和 `version`。
- 更新路径不得依赖进程内 `_parsed_cache` 才能生成合法请求。
- CLI `update-card` 必须使用持久化记录字段重建 Card JSON，而不是假设“刚刚在同一进程里解析过内容”。

补充约束：

- restart-safe 的最低要求是：不同 CLI 进程在共享同一 DB 时仍能完成同一张卡片的后续更新。
- 本契约只要求整卡更新可重建，不在 Plan 3 中扩大到组件级局部重建。

## 10. Live Validation Matrix

Plan 3 文档与实现必须对“哪些是已验证事实、哪些只是文档支持”保持明确区分：

- Second send of successfully sent `card_id` → 由 Task 3 捕获。
- Rejected-first-send retry → 由 Task 3 捕获。
- Stale sequence → 已在 Plan 2 捕获。
- Expiry → 仅 doc-backed，尚未 live-validated。
- Single-send-per-card → 除非 Task 3 证明相反，否则仅按 doc-backed 约束处理。

补充约束：

- live validation 只用于收窄可靠性边界，不应把未观察到的行为扩大解释为通用平台承诺。
- 文档、测试与证据必须同步表达“已验证”“仅文档支持”“需要人工协调”三种不同确定性等级。
