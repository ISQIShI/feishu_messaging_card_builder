# Wrapper-First Seam Sufficiency Audit Entry

## Archival status note

本文件保留为历史性的审计入口清单与证据盘点，不属于当前 closeout contradiction repair 的权威结论面。它本身**不**授权 roadmap advancement、当前 closeout 通过，或任何超出窄范围修复的执行承诺。

## Scope and exclusions

## Evidence inputs

本节固定采用以下证据优先级；低优先级叙事**不能**覆盖高优先级的直接证据：

1. harness/live-validation
2. tests
3. repo docs/memos
4. roadmap/status narrative

若现有仓库只有“间接支持”而没有直接证明，则明确标记为 `assumption-to-validate`，供后续 `## Dimension findings` 与 `## Forced-seam triggers` 使用。

### 1. harness/live-validation

- `.sisyphus/evidence/plan-2/02-recipient-redacted.json`：已有 live recipient lookup 证明 `open_id` / `union_id` 形态存在，可作为 recipient 维度的上游现实约束。
- `.sisyphus/evidence/plan-2/07-contract-delta.md`：已有 live 验证确认 create → send by `card_id` → update → stale-sequence 的官方契约与 `open_id` send path。
- `.sisyphus/evidence/plan-7/task-5-cli-harness-happy.json`：controlled-dual harness 记录 `normalized_event_count=1`、`native_delivery_recorded=true`、`card_create_count=1`、`card_send_count=1`、`entity_first=true`、`status=sent`。
- `.sisyphus/evidence/plan-7/task-5-cli-harness-disabled.json`：disabled harness 记录 `bridge_disabled=true`、`native_delivery_recorded=true`、全部 card op 计数为 0。
- `.sisyphus/evidence/plan-7/task-5-cli-harness-unsupported.json`：unsupported 输入被拦截并保持 `card_create_count/card_send_count/card_update_count = 0`。
- `.sisyphus/evidence/plan-7/task-5-cli-harness-missing-env-proof.json`：缺失 live env 时 fail-closed，`exit_code=1` 且 card op 计数仍为 0。
- `.sisyphus/evidence/plan-7/task-6-reversibility-disabled.json`：独立 reversibility check 再次证明 disabled 模式可回到 native-delivery-only、零 card side effects。
- `.sisyphus/evidence/plan-7/task-8-final-validation.json`：125 tests、CLI help、diff-check 均为 pass，并重索引上述 harness 证据。
- `.sisyphus/evidence/plan-8/task-9-final-validation.json`：Plan 8 最终验证保持 fresh pass，说明当前审计建立在已关闭的 harness/test gate 上。
- `.sisyphus/evidence/plan-8/task-9-plan7-blocker-resolution.json`：cleanup gate 已通过，unsupported/missing-env/privacy/quality blocker 证据均被重新核对。

### 2. tests

- `tests/test_runtime_event.py::test_minimal_text_event_normalizes`：验证 `source_platform/session_key/hermes_message_id/final_reply_index/content_markdown` 与 `recipient_id/recipient_type` 的规范化。
- `tests/test_runtime_event.py::test_unsupported_event_classified`：验证非 `feishu` source 被归类为 unsupported。
- `tests/test_runtime_event.py::test_malformed_event_classified` 与 `::test_missing_core_fields_classified_as_malformed`：验证缺失/非法最终回复字段不会误进入 send path。
- `tests/test_runtime_event.py::test_missing_recipient_classified`：验证缺失 recipient 不会被静默放行。
- `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_controlled_dual_writes_summary`：验证 controlled-dual evidence summary 中 native + card 双侧记录均存在。
- `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_disabled_records_zero_card_ops` 与 `::test_reversibility_disabled_check`：验证 disabled 模式下零 card op 与 native delivery 记录。
- `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_missing_env_uses_tmp_path`：验证缺失凭证时 fail-closed 且不发生 card op。
- `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_malformed_event_is_deterministic`：验证 malformed event 以确定性方式收敛。
- `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_missing_recipient_is_redacted`：验证 missing recipient 进入 redacted classification 路径。
- `tests/test_runtime_bridge_cli.py::test_forbidden_install_surfaces_absent`：验证 repo 根目录不存在不可逆安装/补丁表面。
- `tests/test_runtime_bridge_cli.py::test_cli_help_lists_runtime_bridge` 与 `::test_cli_redacts_expected_bridge_errors`：验证 CLI surface 存在且预期 bridge 错误被 redact，而不是扩大故障面。

### 3. repo docs/memos

- `docs/phase-3-runtime-bridge-design.md`：
  - 23-76 定义 wrapper-first、external websocket outbound observer/wrapper、controlled dual-delivery 仅作验证工具；
  - 88-123 冻结 normalized outbound event contract；
  - 183-214 冻结 failure ceiling 与禁止的自动恢复；
  - 267-280 冻结 reversibility specification；
  - 282-320 冻结 forced-seam escalation triggers 与 stop rule；
  - 340-349 限定当前仍是 harness/offline implementation status。
- `docs/hermes-outbound-seam-memo.md`：给出 Hermes outbound seam 研究、preferred websocket wrapper、dual-delivery fallback、no-patch boundary。
- `docs/phase-1-live-validation.md`：说明 repo 自有 `--live-feishu` 仍是 fail-closed placeholder，live contract 证据来自外部验证而非 repo-owned transport。
- `AGENTS.md`：冻结 websocket-only、entity-first、reversible external changes、no webhook/no patch/no giant-scope drift 等项目硬约束。
- `.sisyphus/evidence/plan-8/wrapper-seam-audit-entry-criteria.md`：保留早期审计 entry criteria、pass/fail matrix 与 forced-seam 触发口径，适合与当前冻结文档对照。

### 4. roadmap/status narrative

- `README.md`：当前状态明确为 Plan 9 wrapper-first seam sufficiency audit，且 Phase 3 仍保持 offline/harness scope。
- `docs/roadmap.md`：Phase 3 目标仍是 websocket 最终回复卡片化、可观测、可恢复、可逆安装边界，而非直接承诺生产 wrapper。
- `docs/open-questions.md`：保留尚未实证的问题，包括最小侵入接缝、recipient 映射、失败恢复、Hermes websocket 行为变化与兼容性。

### Audit-dimension mapping

| Audit dimension | Primary candidate evidence | Current inventory note |
| --- | --- | --- |
| Stable final reply observation | `.sisyphus/evidence/plan-7/task-5-cli-harness-happy.json`; `tests/test_runtime_event.py::test_minimal_text_event_normalizes`; `docs/phase-3-runtime-bridge-design.md` 88-107, 286-289 | `assumption-to-validate`: 现有证据证明 fixture-level final-reply normalization，但尚未直接证明 external websocket wrapper 在真实 Hermes 出站路径上稳定观察最终回复边界。 |
| Recipient identity extraction | `.sisyphus/evidence/plan-2/02-recipient-redacted.json`; `tests/test_runtime_event.py::test_minimal_text_event_normalizes`; `tests/test_runtime_event.py::test_missing_recipient_classified`; `docs/phase-3-runtime-bridge-design.md` 94-103, 298-300 | `assumption-to-validate`: 已证明 recipient 是必要字段且 live send path 使用 `open_id`，但尚未直接证明 wrapper 可从 Hermes websocket 出站安全提取 `recipient_id + recipient_type`。 |
| Native text coexistence/suppression | `.sisyphus/evidence/plan-7/task-5-cli-harness-happy.json`; `.sisyphus/evidence/plan-7/task-5-cli-harness-disabled.json`; `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_controlled_dual_writes_summary`; `docs/phase-3-runtime-bridge-design.md` 61-69, 290-296 | `assumption-to-validate`: controlled dual-delivery 与 disabled fallback 已有证据，但“稳定外部抑制原始文本且无需 Hermes patch”仍未被直接证明。 |
| Reversibility | `.sisyphus/evidence/plan-7/task-6-reversibility-disabled.json`; `.sisyphus/evidence/plan-7/task-8-privacy-scope-closeout.json`; `.sisyphus/evidence/plan-8/task-9-plan7-blocker-resolution.json`; `tests/test_runtime_bridge_cli.py::test_forbidden_install_surfaces_absent`; `docs/phase-3-runtime-bridge-design.md` 267-280 | 当前库存证据最强，既有 disabled-mode proof，也有 forbidden-surface/privacy closeout 与文档硬约束。 |
| Failure ceiling preservation | `.sisyphus/evidence/plan-7/task-5-cli-harness-unsupported.json`; `.sisyphus/evidence/plan-7/task-5-cli-harness-missing-env-proof.json`; `tests/test_runtime_event.py::test_malformed_event_classified`; `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_malformed_event_is_deterministic`; `docs/phase-3-runtime-bridge-design.md` 183-214, 306-308 | `assumption-to-validate`: unsupported/malformed/missing-env 已证明 fail-closed，但外部 wrapper 下 ambiguous send/update → `reconciliation_required` 仍缺直接运行证据。 |
| Forced-seam trigger assessment | `docs/phase-3-runtime-bridge-design.md` 282-320; `.sisyphus/evidence/plan-8/wrapper-seam-audit-entry-criteria.md`; `docs/hermes-outbound-seam-memo.md`; `docs/open-questions.md` | 现有输入足以定义 trigger rubric；是否真正命中 Trigger 1/2/3/4/6/7 仍取决于上述 assumptions 的解释与后续 findings。 |
| Next-step recommendation | `.sisyphus/evidence/plan-7/task-8-final-validation.json`; `.sisyphus/evidence/plan-8/task-9-final-validation.json`; `README.md`; `docs/roadmap.md`; `docs/open-questions.md`; `docs/phase-3-runtime-bridge-design.md` 318-349 | `assumption-to-validate`: 推荐值可由现有通过基线收窄范围，但最终只能建立在前述 observation/recipient/suppression/failure-ceiling 结论之上。 |

### Assumptions requiring validation

- `stable_final_reply_observation`: `assumption-to-validate` — 需要额外证明 external websocket wrapper 无需内部 Hermes seam 即可稳定观察最终回复边界。
- `recipient_identity_extraction`: `assumption-to-validate` — 需要额外证明 wrapper 可在生产语义下安全抽取 `recipient_id + recipient_type`。
- `native_text_coexistence_suppression`: `assumption-to-validate` — 需要额外证明外部 wrapper 可稳定抑制原始文本，或证明长期 dual-delivery 仍不违背产品边界。
- `failure_ceiling_preservation`: `assumption-to-validate` — 需要额外证明 ambiguous send/update 能安全收敛到 `reconciliation_required`，而不是只覆盖 malformed/unsupported/missing-env。
- `forced_seam_trigger_assessment`: `assumption-to-validate` — Trigger 7（所需语义只能由 Hermes 内部 seam 提供）目前仍是 memo-level hypothesis，尚无直接对照证据。
- `next_step_recommendation`: `assumption-to-validate` — Task 4/5 必须先对以上假设给出 `pass/constraint/fail`，再决定 recommendation。

## Sufficiency rubric

This rubric defines the classification logic for evaluating the sufficiency of the wrapper-first integration seam.

### Dimension status vocabulary

Every audit dimension must be assigned exactly one of these three status values:

- `pass`: Evidence conclusively supports that the wrapper-first seam can handle this dimension without structural changes to Hermes.
- `constraint`: Evidence supports capability BUT with explicit limitations or conditions that must be documented and mitigated.
- `fail`: Evidence shows wrapper-first seam cannot handle this dimension, OR evidence is contradictory/missing.

**Critical Rule:** Contradictory or missing evidence forces `fail` for that dimension and cannot be upgraded by narrative confidence.

### Overall outcome vocabulary

The overall sufficiency outcome is derived from the dimension statuses:

- `wrapper-sufficient`: ALL dimensions pass with evidence.
- Legacy deprecated constrained-wrapper label: No dimension fails, BUT at least one dimension has an explicit `constraint` with documented mitigation. The final recommendation must use `wrapper-first-with-constraints` instead.
- `wrapper-insufficient`: ANY dimension fails, OR evidence is contradictory/inconclusive.

### Decision thresholds

- **Move from `constraint` to `fail`**: When evidence shows fundamental incompatibility with the wrapper-first approach or when mitigation for a constraint breaks a project non-negotiable (e.g., reversibility).
- **Move from `pass` to `constraint`**: When evidence shows capability but requires specific environmental assumptions, operational overhead, or non-standard configuration that must be tracked.
- **Forced Failure**: Any match with the `Forced-Seam Escalation Triggers` defined in `docs/phase-3-runtime-bridge-design.md` requires an immediate `fail` for the affected dimension and an overall `wrapper-insufficient` outcome.


## Dimension findings

### 1. Stable final reply observation

- **Status**: `constraint`
- **Question**: Can the external wrapper stably observe Hermes final reply boundaries?
- **Evidence**:
  - `.sisyphus/evidence/plan-7/task-5-cli-harness-happy.json`
  - `tests/test_runtime_event.py::test_minimal_text_event_normalizes`
  - `docs/phase-3-runtime-bridge-design.md` 88-123, 286-289
- **Assumptions**: 现有证据只证明 fixture/harness 层可以规范化 `source_platform + session_key + hermes_message_id + final_reply_index`，尚未直接证明 external websocket wrapper 在真实 Hermes 出站流量上可以稳定观测最终回复边界。
- **Constraints**: 当前 Phase 3 仍是 harness/offline scope；若没有额外 wrapper-level runtime 证据，就不能把“能稳定观测最终回复”提升为 `pass`。
- **Decision impact**: 该维度允许继续保留 wrapper-first 方向，但总体建议必须携带“real external observation 仍待验证”的约束；若后续证据显示无法稳定观测，则会直接命中 Trigger 1，并把整体结果推向 forced-seam decision memo。

### 2. Recipient identity extraction

- **Status**: `constraint`
- **Question**: Can recipient identifier and type be safely extracted from Hermes outbound traffic?
- **Evidence**:
  - `.sisyphus/evidence/plan-2/02-recipient-redacted.json`
  - `.sisyphus/evidence/plan-2/07-contract-delta.md`
  - `tests/test_runtime_event.py::test_minimal_text_event_normalizes`
  - `tests/test_runtime_event.py::test_missing_recipient_classified`
  - `docs/phase-3-runtime-bridge-design.md` 94-103, 298-300
- **Assumptions**: 已知 live send path 以 `open_id` 为现实约束，且测试证明 recipient 字段是必要输入；但 wrapper 能否从 Hermes websocket 出站安全提取 `recipient_id + recipient_type` 仍是 `assumption-to-validate`。
- **Constraints**: 在没有真实 external wrapper 抽取证据前，不能宣称 recipient extraction 已满足最小可审计投递条件；缺失 recipient 的现有结论仅证明 fail-closed guard 存在，不证明生产抽取一定可行。
- **Decision impact**: 该维度阻止“无条件继续 wrapper-first”；后续 recommendation 只能建立在补充 recipient extraction 证据或明确外部提取策略的前提上。若无法安全抽取，将命中 Trigger 4。

### 3. Native text coexistence/suppression

- **Status**: `constraint`
- **Question**: Can native text delivery be suppressed or safely coexist with card delivery?
- **Evidence**:
  - `.sisyphus/evidence/plan-7/task-5-cli-harness-happy.json`
  - `.sisyphus/evidence/plan-7/task-5-cli-harness-disabled.json`
  - `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_controlled_dual_writes_summary`
  - `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_disabled_records_zero_card_ops`
  - `docs/phase-3-runtime-bridge-design.md` 61-69, 208-214, 290-296
- **Assumptions**: controlled-dual harness 证明 native + card 双侧记录在验证环境中可并存，disabled 模式证明可退回 native-only；但“外部 wrapper 能稳定抑制原始文本，且无需 Hermes patch”仍未被直接证明。
- **Constraints**: **dual-delivery 仅是验证/取证工具，不是产品默认行为。** 当前证据支持受控 coexistence 与 disabled fallback，但不支持把长期双发或稳定抑制原文视为已验证能力。
- **Decision impact**: 建议层面必须禁止把 dual-delivery 当默认产品路径；若后续发现必须长期双发，或抑制原文必须修改 Hermes 源码，将分别命中 Trigger 2 或 Trigger 3，并迫使 wrapper-first 退出默认路线。

### 4. Reversibility

- **Status**: `pass`
- **Question**: Does the wrapper path preserve reversible integration boundaries?
- **Evidence**:
  - `.sisyphus/evidence/plan-7/task-6-reversibility-disabled.json`
  - `.sisyphus/evidence/plan-7/task-8-privacy-scope-closeout.json`
  - `.sisyphus/evidence/plan-8/task-9-plan7-blocker-resolution.json`
  - `tests/test_runtime_bridge_cli.py::test_forbidden_install_surfaces_absent`
  - `docs/phase-3-runtime-bridge-design.md` 267-280
- **Assumptions**: 该结论仍以当前 memo-only / harness-only 边界为前提；若未来实现引入仓库外脚本、不可审计补丁或不可回滚环境改动，需要重新审核。
- **Constraints**: 当前证据下没有额外功能性约束；唯一边界是不得突破 `docs/phase-3-runtime-bridge-design.md` 267-280 与 `AGENTS.md` 冻结的可逆性红线。
- **Decision impact**: 这是目前最强的正向维度，允许 recommendation 保持在 wrapper-first 家族内，而不是立即失败；只有当未来实现破坏 disabled mode、zero card ops 或 forbidden surfaces 约束时，才会触发 Trigger 5。

### 5. Failure ceiling preservation

- **Status**: `constraint`
- **Question**: Can the wrapper preserve failure ceiling (converge to reconciliation_required)?
- **Evidence**:
  - `.sisyphus/evidence/plan-7/task-5-cli-harness-unsupported.json`
  - `.sisyphus/evidence/plan-7/task-5-cli-harness-missing-env-proof.json`
  - `tests/test_runtime_event.py::test_unsupported_event_classified`
  - `tests/test_runtime_event.py::test_malformed_event_classified`
  - `tests/test_runtime_event.py::test_missing_core_fields_classified_as_malformed`
  - `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_malformed_event_is_deterministic`
  - `docs/phase-3-runtime-bridge-design.md` 183-214, 306-308
- **Assumptions**: 现有 harness/test 证明 unsupported、malformed、missing-env 会 fail-closed，并且不扩张 card side effects；但 send/update ambiguous 场景如何在 external wrapper 下稳定收敛到 `reconciliation_required` 仍缺直接证据。
- **Constraints**: 相对 native-text-only baseline，wrapper 目前只被证明在“前置拒绝类失败”上不会扩大事故面；对 ambiguous send/update、remote-success-local-failure、state-reuse ambiguity 等冻结场景，仍只能依赖设计文档约束，不能宣称已经 runtime 证明。
- **Decision impact**: recommendation 只能接受“failure ceiling contract 已定义且部分验证”，不能把其写成生产就绪承诺；若后续 wrapper 无法把 ambiguous send/update 收敛到 `reconciliation_required`，将命中 Trigger 6。

### 6. Forced-seam trigger assessment

- **Status**: `constraint`
- **Question**: Which forced-seam triggers from Phase 3 design are relevant?
- **Evidence**:
  - `docs/phase-3-runtime-bridge-design.md` 282-320
  - `.sisyphus/evidence/plan-8/wrapper-seam-audit-entry-criteria.md`
  - `docs/hermes-outbound-seam-memo.md`
  - `docs/open-questions.md`
- **Assumptions**: Trigger 1-7 已有冻结定义，但当前大多仍处于“relevant but not yet empirically triggered”状态；其中 Trigger 1/2/3/4/6/7 依赖前述 observation/recipient/suppression/failure-ceiling 缺口，Trigger 5 则被当前 reversibility evidence 暂时压低风险。
- **Constraints**: 本维度只能确认触发器集合完整且与当前审计相关，不能提前宣告任何 observation/recipient/suppression/failure-ceiling 触发器已经被真实运行证据命中或排除。
- **Decision impact**: 总体 recommendation 必须把 Trigger 1-7 当作后续 stop-rule，而不是把 wrapper-first 写成默认可落地方案；尤其 Trigger 1/2/3/4/6/7 需要在下一步验证中被主动对照，Trigger 5 则要求保持当前可逆边界不漂移。

### 7. Next-step recommendation foundation

- **Status**: `constraint`
- **Question**: Is there sufficient foundation to make a recommendation?
- **Evidence**:
  - `.sisyphus/evidence/plan-7/task-8-final-validation.json`
  - `.sisyphus/evidence/plan-8/task-9-final-validation.json`
  - `README.md`
  - `docs/roadmap.md`
  - `docs/open-questions.md`
  - `docs/phase-3-runtime-bridge-design.md` 318-349
- **Assumptions**: Plan 7/8 已证明 harness、tests、CLI help、diff-check 的关闭条件成立，因此 recommendation 可以建立在已关闭的 offline baseline 上；但 recommendation 仍受前六个维度的 `constraint` 约束，不能跳过这些缺口。
- **Constraints**: 由于 stable final reply observation、recipient extraction、native text suppression/coexistence、failure ceiling 与 forced-seam assessment 都未到 `pass`，推荐基础只足以支持 `wrapper-first-with-constraints` 方向，不足以支持无约束的 `continue-wrapper-first`。
- **Decision impact**: 该维度为后续 `## Recommendation` 提供收束依据：当前最合理结果应是保留 wrapper-first 作为下一步验证基础，但明确带约束推进；若任一关键约束后续转为 `fail`，则 recommendation 必须升级为 separate forced-seam decision memo。

## Forced-seam triggers

本节按 `docs/phase-3-runtime-bridge-design.md` 282-320 的冻结口径，对 7 个 forced-seam trigger 做客观对照。`triggered` 只能取 `yes` / `no` / `inconclusive`：

- `yes`：现有证据已经证明触发条件成立，必须停止 wrapper-first 默认推进。
- `no`：现有证据足以证明当前**尚未**命中该触发条件，但不代表未来实现自动安全。
- `inconclusive`：现有证据不足以确认 `yes` 或 `no`，因此 recommendation 只能保持约束式推进。

### Trigger 1: Cannot observe stable final replies

- **Triggered**: `inconclusive`
- **Definition check**: 该触发器要求 external wrapper **无法稳定**导出 `source_platform + session_key + hermes_message_id + final_reply_index`。
- **Evidence**:
  - `## Dimension findings` → `### 1. Stable final reply observation`
  - `.sisyphus/evidence/plan-7/task-5-cli-harness-happy.json`
  - `tests/test_runtime_event.py::test_minimal_text_event_normalizes`
  - `docs/phase-3-runtime-bridge-design.md` 286-289
- **Evidence source**: 受控 harness/test normalization 证据，仅证明 fixture/mock 入口上的 final-reply contract；不包含真实 Hermes websocket outbound observation。
- **Threshold for `no`**: 需要 real external wrapper observation 直接证明在代表性 websocket outbound 流量下，`source_platform + session_key + hermes_message_id + final_reply_index` 可稳定导出。
- **Failure condition for `yes`**: 需要直接证据证明 external wrapper **无法稳定**观察最终回复边界，或该边界在真实 wrapper 场景下系统性丢失/漂移。
- **Assessment**: 当前已有 harness/test 级别证据证明 final-reply normalization 契约在受控环境中成立，因此尚未实证命中 `yes`。但由于 real external wrapper observation 仍是 `assumption-to-validate`，现有材料也不足以客观排除该触发器；因此本项必须写成 `inconclusive`，而不是 `no`。
- **Consequence**: 若后续 real wrapper evidence 证明无法稳定观察最终回复边界，则该触发器立即转为 `yes`，并对 Dimension 1 形成直接 `fail`，整体结论升级为 `wrapper-insufficient`。
- **Recommendation impact**: 当前允许保留 wrapper-first 方向，但 recommendation 必须显式写明“stable final reply observation 仍待 real wrapper 验证”，且不能把本项表述成 plain continuation 所需的已排除风险。

### Trigger 2: Cannot suppress or safely coexist with original text send

- **Triggered**: `inconclusive`
- **Definition check**: 该触发器要求 wrapper 既无法抑制原始文本，又无法把 dual-delivery 限制在受控验证阶段，导致双发成为常态产品行为。
- **Evidence**:
  - `## Dimension findings` → `### 3. Native text coexistence/suppression`
  - `.sisyphus/evidence/plan-7/task-5-cli-harness-happy.json`
  - `.sisyphus/evidence/plan-7/task-5-cli-harness-disabled.json`
  - `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_controlled_dual_writes_summary`
  - `docs/phase-3-runtime-bridge-design.md` 61-69, 290-292
- **Evidence source**: 设计冻结文本 + harness 受控 dual-delivery evidence，只证明 validation-only 边界在离线/受控环境中成立。
- **Threshold for `no`**: 需要 external wrapper 层面的直接证据，证明原始文本可被稳定抑制，或 dual-delivery 能在真实运行中持续受限于 validation-only 边界而不会滑入默认产品行为。
- **Failure condition for `yes`**: 需要直接证据证明 wrapper 既无法抑制原始文本，又无法把 dual-delivery 限制在受控验证阶段，导致双发成为常态产品行为。
- **Assessment**: 现有设计冻结与 harness evidence 一致表明 dual-delivery 目前**被定义为** validation/evidence gathering 工具，而不是产品默认路径，因此尚未实证命中 `yes`。但当前材料仍缺少 external wrapper 层面的直接 suppression/coexistence 证据，无法客观排除未来只能依赖长期双发的可能，因此本项也必须写成 `inconclusive`。
- **Consequence**: 若后续 wrapper 只能依赖长期双发才能工作，且无法继续维持 validation-only 边界，则该触发器转为 `yes`，必须停止把 wrapper-first 当默认产品路线。
- **Recommendation impact**: recommendation 必须继续禁止把 dual-delivery 写成默认产品行为，并把“suppression/coexistence 仍待 wrapper-level 直接验证”列为继续推进的显式约束，而不是把当前状态当成 plain continuation 许可。

### Trigger 3: Preventing duplicate native text requires Hermes source patching

- **Triggered**: `inconclusive`
- **Definition check**: 该触发器要求“稳定抑制原始文本”只有在修改 Hermes 核心源码时才可实现。
- **Evidence**:
  - `## Dimension findings` → `### 3. Native text coexistence/suppression`
  - `docs/phase-3-runtime-bridge-design.md` 294-296
  - `docs/hermes-outbound-seam-memo.md`
  - `AGENTS.md` non-negotiables / anti-patterns
- **Assessment**: 当前仓库明确冻结 no-patch boundary，也没有任何证据证明外部 wrapper 已经成功完成稳定 suppression；但同样没有证据证明 suppression **必须** 依赖 Hermes source patch。因此本项既不能写成 `no`，也不能提前写成 `yes`，只能保持 `inconclusive`。
- **Consequence**: 如果后续验证表明“防止重复原文显示”的唯一稳定方案是改 Hermes core source，本触发器立刻转为 `yes`，并要求直接停下产出 Forced-Seam Decision Memo，而不是进入 patch 实施讨论。
- **Recommendation impact**: 只要本项仍为 `inconclusive`，总体 recommendation 就不能是 `wrapper-first-with-constraints` 以外的无约束路径。

### Trigger 4: Recipient identity cannot be extracted safely

- **Triggered**: `inconclusive`
- **Definition check**: 该触发器要求无法稳定获得 `recipient_id + recipient_type`，使 send path 失去最小可审计投递条件。
- **Evidence**:
  - `## Dimension findings` → `### 2. Recipient identity extraction`
  - `.sisyphus/evidence/plan-2/02-recipient-redacted.json`
  - `.sisyphus/evidence/plan-2/07-contract-delta.md`
  - `tests/test_runtime_event.py::test_missing_recipient_classified`
  - `docs/phase-3-runtime-bridge-design.md` 298-300
- **Assessment**: 已知 live send path 使用 `open_id`，且 tests/harness 明确 recipient 是必要字段；但 external wrapper 能否从真实 Hermes websocket 出站安全抽取 `recipient_id + recipient_type` 仍未被直接证明。因此本项不能写 `no`，因为尚无 wrapper-level extraction success；也不能写 `yes`，因为尚无 wrapper-level extraction failure。
- **Consequence**: 若后续确认 recipient identity 无法稳定抽取，本触发器转为 `yes`，并直接阻断 minimum auditable delivery condition。
- **Recommendation impact**: recommendation 必须把 recipient extraction 列为继续 wrapper-first 前的关键验证前提之一。

### Trigger 5: Wrapper path breaks reversibility

- **Triggered**: `no`
- **Definition check**: 该触发器要求 wrapper 需要不可安装、不可卸载、不可恢复、不可审计的 Hermes 或环境改动。
- **Evidence**:
  - `## Dimension findings` → `### 4. Reversibility`
  - `.sisyphus/evidence/plan-7/task-6-reversibility-disabled.json`
  - `.sisyphus/evidence/plan-7/task-8-privacy-scope-closeout.json`
  - `.sisyphus/evidence/plan-8/task-9-plan7-blocker-resolution.json`
  - `tests/test_runtime_bridge_cli.py::test_forbidden_install_surfaces_absent`
  - `docs/phase-3-runtime-bridge-design.md` 302-304
- **Assessment**: 当前 reversibility 维度是唯一明确 `pass`，且 disabled-mode / zero-card-op / forbidden-surface evidence 彼此一致，因此没有证据显示 wrapper path 已破坏可逆边界。本项是 7 个 trigger 中风险最低、当前最接近明确排除的触发器。
- **Consequence**: 若未来实现引入不可回滚环境改动、不可审计补丁或破坏 disabled fallback，本触发器将从 `no` 转为 `yes`，并立即触发 stop rule。
- **Recommendation impact**: 当前 recommendation 可以继续保留 wrapper-first 家族路径，但必须继续受 reversibility red line 约束。

### Trigger 6: Wrapper path cannot preserve failure ceiling

- **Triggered**: `inconclusive`
- **Definition check**: 该触发器要求 wrapper 会系统性地产生 ambiguous send/update，且无法安全收敛为 `reconciliation_required`。
- **Evidence**:
  - `## Dimension findings` → `### 5. Failure ceiling preservation`
  - `.sisyphus/evidence/plan-7/task-5-cli-harness-unsupported.json`
  - `.sisyphus/evidence/plan-7/task-5-cli-harness-missing-env-proof.json`
  - `tests/test_runtime_event.py::test_malformed_event_classified`
  - `tests/test_runtime_bridge_cli.py::test_runtime_bridge_harness_malformed_event_is_deterministic`
  - `docs/phase-3-runtime-bridge-design.md` 306-308
- **Assessment**: 现有 evidence 只充分覆盖 malformed / unsupported / missing-env 等 fail-closed 前置拒绝场景；对 ambiguous send/update 是否能在 external wrapper 下安全收敛为 `reconciliation_required`，仍无 runtime-level direct proof。因此本项必须保持 `inconclusive`。
- **Consequence**: 若后续真实 wrapper 行为显示 ambiguous send/update 无法安全收敛，本触发器即转为 `yes`，并构成 frozen failure ceiling contract 的直接破坏。
- **Recommendation impact**: recommendation 只能把 failure ceiling 写成“contract frozen and partially validated”，不能写成生产级已验证结论。

### Trigger 7: Required semantics demand internal Hermes seam

- **Triggered**: `inconclusive`
- **Definition check**: 该触发器要求最小目标所需语义——最终回复边界、recipient identity、发送抑制或状态同步——只有 Hermes 内部 seam 才能提供，且已有书面证据证明 external wrapper 不足。
- **Evidence**:
  - `## Dimension findings` → `### 1-6`
  - `docs/phase-3-runtime-bridge-design.md` 310-320
  - `docs/hermes-outbound-seam-memo.md`
  - `docs/open-questions.md`
- **Assessment**: 当前多个核心维度仍是 `constraint`，说明 external wrapper sufficiency 尚未被证明；但现有材料还没有形成“只有内部 Hermes seam 才能满足最小目标”的书面定论。因此本项不能写 `no`（因为关键语义缺口仍在），也不能写 `yes`（因为 external wrapper insufficiency 尚未被直接证明到 forced-seam 级别）。
- **Consequence**: 若任一关键语义被证实只能由 Hermes 内部 seam 提供，本触发器转为 `yes`，并要求单独产出 Forced-Seam Decision Memo，而不是在 Plan 9 中提前设计实现。
- **Recommendation impact**: 由于本项仍 `inconclusive`，总体 recommendation 不能是 plain `continue-wrapper-first`，只能是 `wrapper-first-with-constraints`。

### Escalation rule summary

- **Rule restatement**: 如果任一 trigger 从当前的 `no` / `inconclusive` 转为 `yes`，必须停止把 wrapper-first 当作默认实现路径。
- **Required response**: 停下当前 wrapper-first 推进，产出 **Forced-Seam Decision Memo**，说明首选接缝为何失效、为何新接缝更可逆、以及如何安装 / 审计 / 回滚。
- **Explicit boundary**: Forced-Seam Decision Memo 是**未来单独计划项**，不是 Plan 9 的实现任务；本审计只负责定义 stop conditions 和 recommendation 约束，不设计 forced seam，也不提议 Hermes patch。
- **Recommendation consistency**: 由于 Trigger 1 / 2 / 3 / 4 / 6 / 7 当前均为 `inconclusive`，且只有 Trigger 5 被明确排除，当前 recommendation 只能落在 **wrapper-first-with-constraints**，不能落在无条件继续或生产就绪表述。这里的 `inconclusive` 代表“尚未证明必须 forced seam”，但也同样代表“尚未证明 wrapper-first 风险已被排除”，因此它们产生的是推进约束，而不是立即切换接缝的既成结论。

## Recommendation

### Exact recommendation
`wrapper-first-with-constraints`

### Rationale
Dimension evaluation results show that while the core integration logic is sound and the reversibility red line is preserved (`pass`), 6 out of 7 dimensions are marked as `constraint`. Furthermore, 6 out of 7 escalation triggers are `inconclusive`, with only Trigger 5 currently ruled out by direct reversibility evidence. This pattern indicates that there are no immediate blockers (`fail`) or proven forced-seam conditions (`yes`) today, but the project still lacks direct runtime evidence for key production behaviors like real-world websocket observation, recipient extraction, and stable text suppression/coexistence. Therefore, an unconditional "continue-wrapper-first" is not supported, while an immediate forced-seam decision would also overclaim beyond the current evidence. The correct posture is to continue only under explicit constraints, entry criteria, and stop-rules.

### Constraints list
- **Observation Constraint**: Stable final reply observation is currently verified at the fixture/harness level only. Success in real-world Hermes websocket outbound traffic remains an assumption to be validated.
- **Trigger-objectivity Constraint**: Trigger 1 and Trigger 2 are `inconclusive` because current evidence is strong enough to reject immediate `yes`, but not strong enough to justify `no`. That means they constrain continuation and require explicit next-step proof, rather than forcing a seam change now.
- **Identity Constraint**: Recipient identity extraction (ID and type) from the websocket stream has not been proven. The current proof only shows that the send path requires these identifiers.
- **Suppression Constraint**: Native text suppression without core repository modifications is not yet demonstrated. Dual-delivery is strictly a validation tool and must not become the product default.
- **Ceiling Constraint**: The failure ceiling contract for ambiguous send/update operations (converging to `reconciliation_required`) lacks direct runtime verification in a wrapper context.
- **Monitoring Requirement**: All `inconclusive` triggers (1, 2, 3, 4, 6, and 7) must be actively monitored. Any shift to a `yes` status requires an immediate halt.

### Stop conditions
If any of the following triggers transition to `yes`, the wrapper-first approach must be immediately halted, and a **Forced-Seam Decision Memo** must be created:
1. Cannot observe stable final replies (Trigger 1).
2. dual-delivery becomes a permanent product behavior (Trigger 2).
3. Native text suppression requires Hermes source patching (Trigger 3).
4. Recipient identity cannot be extracted safely (Trigger 4).
5. Implementation breaks reversibility (Trigger 5).
6. Failure ceiling contract is violated by ambiguous states (Trigger 6).
7. Required semantics are proven to be exclusive to internal Hermes seams (Trigger 7).

### Next-step entry criteria
Transitioning out of the current audit phase requires:
1. Direct evidence of successful external wrapper observation of Hermes final replies.
2. Verified proof of recipient extraction from live or representative websocket traffic.
3. Feasibility confirmation for native text suppression without repository patches.
4. Runtime validation of ambiguous send/update failure ceiling handling.

## Explicit non-goals

The following scopes are strictly excluded from current and immediate future implementation cycles:
- **No live websocket bridge implementation**: No production bridge or live transport logic.
- **No production wrapper deployment**: No deployment or operation of an external wrapper service.
- **No Hermes source patch**: No monkey patching, core source modification, or forced-seam code in Hermes.
- **No webhook handling**: No endpoint design, signature validation, or HTTP request URL processing.
- **No installer suite**: No automated installation, update, check, or uninstall script implementations.
- **No queue/retry engine**: No background processing for retries, reconciliation, or deduplication.
- **No service deployment**: No containerization, orchestration, or service-level management.
- **No streaming/process-message cardification**: No support for partial streams, tool-call summaries, or intermediate agent thoughts.
- **No card actions**: No interaction callbacks, button handlers, or interactive flow processing.
- **No component-level partial update**: Only whole-card replacement is supported.
- **No broad content-model abstraction**: No attempt to create a multi-platform or generic content model.
- **No prototype code or code spike**: Implementation is limited to harness/test/documentation scopes.
- **No broad README/product rewrite**: No marketing or product repositioning beyond current-stage status updates.
