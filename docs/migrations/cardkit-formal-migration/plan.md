# Feishu CardKit 正式链路迁移方案设计

> 适用项目：`/root/feishu_messaging_card_builder`
>
> 目标：在**不直接修改 Hermes 主仓**的前提下，通过 `run.py.patch` + `feishu_card_build/` 工具目录，实现从“interactive 最终态卡片直发”到“CardKit 正式链路”的分阶段迁移，并保留稳定 fallback。

---

## 0. 文档使用说明

### 0.1 这份文档解决什么问题

这不是一份泛泛而谈的调研记录，而是供后续实施直接跟着执行的迁移设计稿。它回答三类问题：

1. **为什么要迁移**：当前 interactive 直发链路的边界是什么，CardKit 能解决哪些问题。
2. **迁移到什么程度**：首版做什么、不做什么，怎样保留 fallback，避免把现有稳定能力一次性推翻。
3. **具体怎么做**：到文件级、配置级、测试级、阶段拆分级别的实施建议。

### 0.2 实施约束

后续若按本方案实施，必须继续遵守以下约束：

- **只修改工具目录与 `run.py.patch`**
- **不直接修改 Hermes 主仓已安装文件**
- **不自动安装、不自动更新、不自动重启**，除非用户明确授权
- patch 维护方式继续保持：
  - 普通 unified diff
  - 在 `$HERMES_HOME` 下应用
  - `patch -p0`

### 0.3 推荐阅读顺序

1. 先读 **第 2 节** 看长度/频率限制与迁移收益
2. 再读 **第 7 节** 看推荐迁移流程
3. 然后读 **第 16 节** 的实施任务清单
4. 最后按 **第 17 节** 的里程碑推进

---

## 1. 背景与结论

当前工具的实际发送方式是：

1. `feishu_card_build` 生成卡片 JSON
2. `run.py.patch` 调用 Feishu 适配器
3. 通过 `msg_type="interactive"` 直接发送卡片消息

这条链路本身是**官方支持的交互式卡片消息发送方式**，但它**不是**官方 CardKit 的完整实体化链路。

如果要支持以下能力：

- 正文逐字打字机式流式输出
- 按 `element_id` 局部更新指定组件
- 更平滑的“生成中 → 完成”状态切换
- 后续在正文下动态追加组件（如反馈入口、操作按钮、状态标记）

则应迁移到 **CardKit card entity + card element/card settings OpenAPI** 正式链路。

---

## 2. 关于长度限制：CardKit 链路是否还有消息长度限制？

结论：**有，CardKit 并不会消除长度限制，只是把限制从“单条 interactive 消息整包提交”转移为“卡片 JSON 结构限制 + CardKit OpenAPI 请求体限制 + 组件数量限制 + 更新频率限制”。**

### 2.1 已查到的官方明确限制

以下结论来自飞书官方文档 markdown 版本：

#### A. 卡片 JSON 2.0 结构限制
来源：
- `https://open.feishu.cn/document/feishu-cards/card-json-v2-structure.md`

明确限制：
- **一张卡片最多支持 200 个元素（elements）或组件**
- `update_multi` 在 JSON 2.0 中目前**仅支持 `true`**
- `width_mode` 可用，但与长度无直接关系

这说明即使迁移到 CardKit，**单卡结构复杂度仍然有限**，不能无限追加组件。

#### B. 创建卡片实体（Create card entity）请求体限制
来源：
- `https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/cardkit-v1/card/create.md`

明确限制：
- `data`（卡片 JSON 转义后的字符串）长度范围：**1 ～ 3,000,000 字符**
- 一个 card entity：**仅支持发送一次**
- card entity 有效期：**14 天**
- API 频率限制：**1000 次/分钟，50 次/秒**

这说明 CardKit 在“创建阶段”可承载的卡片 JSON 体积，远高于普通直发卡片常见可接受体量，但**依然不是无限制**。

#### C. 全量更新卡片实体（Update card）请求体限制
来源：
- `https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/cardkit-v1/card/update.md`

明确限制：
- `data`（更新后的卡片 JSON 字符串）长度范围：**1 ～ 1,000,000 字符**
- `uuid` 长度范围：**1 ～ 64 字符**
- `sequence`：**1 ～ 2147483647**，且必须严格递增
- API 频率限制：**1000 次/分钟，50 次/秒**

这说明 CardKit 的全量更新虽然比 message 级编辑灵活，但仍然存在**请求体长度上限**。

#### D. 更新卡片配置（Update card settings）请求体限制
来源：
- `https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/cardkit-v1/card/settings.md`

明确限制：
- `settings`（配置 JSON 转义后的字符串）长度范围：**1 ～ 100,000 字符**
- `uuid` 长度范围：**1 ～ 64 字符**
- `sequence`：**1 ～ 2147483647**，且必须严格递增
- API 频率限制：**1000 次/分钟，50 次/秒**

这对于我们要做的“流式结束后关闭 `streaming_mode`”完全足够，但仍然说明**配置更新也不是无限制**。

#### E. 流式更新总览中的频率限制
来源：
- `https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/streaming-updates-openapi-overview.md`

明确限制：
- 对于**单个卡片实体**，使用卡片和组件级 OpenAPI 操作卡片的频率上限为：**10 次/秒**

这条对迁移尤其关键：
- 即使正文用流式输出，也不能无限高频地推送更新
- 需要在 gateway 侧做节流与批量聚合

### 2.2 当前已确认、但未在本轮拿到更细粒度数值的点

本轮已拿到官方总览文档，明确确认了：
- CardKit 支持流式更新文本
- `plain_text` / `markdown` 可作为流式目标
- `streaming_mode`、`print_step`、`print_strategy` 等能力存在

但**本轮直接抓取到的官方 markdown 页面里，尚未拿到“单次 Streaming update text 请求体 content 的明确字符上限字段”**。

因此当前可以严谨下结论的是：

1. **CardKit 仍然有明确长度/结构/频率限制**
2. 它的上限整体上**比当前单次 interactive 最终卡片直发更宽松、更适合演进式更新**
3. 但它**并不意味着可以不做拆分、截断、节流和组件数控制**

### 2.3 对本项目的实际含义

迁移到 CardKit 后：

- **不会**消除所有长度问题
- **会**显著改善以下问题：
  - 不必每次都重发整张卡
  - 可以把“生成中正文”和“完成态正文”拆为多次更新
  - 可以减少单次提交的峰值体积
  - 可以把工具/思考/正文/反馈入口拆成更稳定的演进式卡片结构

因此，对本项目来说：

> CardKit 的核心收益不是“无限长度”，而是“更好的可更新性、可拆分性、可节流性和可扩展性”。

---

## 3. 迁移目标

### 3.1 主目标

在工具目录内完成一套可安装的正式链路方案，使 Feishu 最终卡片支持：

1. 创建 CardKit card entity
2. 发送该 card entity
3. 对正文 `markdown` 元素进行**逐字打字机式流式更新**
4. 输出完成后关闭 `streaming_mode`
5. 如有需要，追加完成态组件或局部更新 footer/面板
6. 任意阶段失败时可回退到现有 interactive 直发或原始文本链路

### 3.2 非目标

本次迁移方案不追求：
- 一次性移除当前 interactive 最终卡片直发链路
- 在首版中同时完成所有组件级局部更新能力
- 在首版中把所有中间过程消息都卡片化
- 在未验证稳定前，默认替换现有所有 Feishu 最终消息发送路径

### 3.3 验收定义

只有同时满足以下条件，才算“正式链路可用”：

1. `transport_mode=cardkit` 时，最终回复能够创建并成功发送 card entity
2. `enable_streaming=true` 时，正文能以**逐字视觉效果**完成流式更新
3. 流式结束后，`streaming_mode` 被明确关闭
4. 失败时能回退到 interactive 或文本，不丢最终答案
5. 单测与 mock 集成测试覆盖关键时序与 fallback 分支

---

## 4. 设计原则

1. **只改工具目录和 `run.py.patch`**
   - 不直接修改已安装 Hermes 主仓文件

2. **双轨并存，逐步迁移**
   - 保留当前 interactive final card 作为 fallback
   - 新增 CardKit 正式链路作为增强模式

3. **builder 与发送职责分离**
   - `feishu_card_build/` 负责构造卡片 JSON 与 streaming 元信息
   - gateway patch / adapter 才负责 CardKit API 调用

4. **始终可回退**
   - create/send/update/disable-streaming 任一步失败，都不应阻断最终答复

5. **严格遵守官方流式语义**
   - `print_step = 1`
   - `print_strategy = "delay"`
   - 结束后显式关闭 `streaming_mode`

6. **控制单卡复杂度与更新频率**
   - 保留组件数预算
   - 为单卡 OpenAPI 操作做节流（<= 10 次/秒）

7. **先最小可用，再增强**
   - 先打通 create/send
   - 再打通正文 streaming
   - 再增加完成态增强与局部更新

---

## 5. 现状与目标链路对比

### 5.1 当前链路

```text
agent_result
  -> run.py.patch 组装 payload
  -> feishu_card_build 生成 cards
  -> adapter._feishu_send_with_retry(msg_type="interactive")
  -> 最终态整卡发送
```

特点：
- 简单
- 稳定
- 适合最终态静态卡片
- 不支持真正的正文流式 / 局部更新

### 5.2 目标链路

```text
agent_result
  -> run.py.patch 组装 payload
  -> feishu_card_build 生成：
       - initial_card
       - final_cards / final_state
       - streaming_element_id
       - streaming_content
       - optional element map
  -> gateway patch 获取 tenant_access_token
  -> POST /cardkit/v1/cards 创建 card entity
  -> 发送 card_id 到 Feishu 会话
  -> PUT streaming text API 连续更新正文
  -> PATCH /cardkit/v1/cards/:card_id/settings 关闭 streaming_mode
  -> 可选：PUT/PATCH 完成态更新
  -> 若失败：fallback 到 interactive 直发 / 文本
```

### 5.3 能力对比表

| 能力 | 当前 interactive 直发 | 目标 CardKit 链路 |
|---|---|---|
| 最终态静态卡片 | 支持 | 支持 |
| 正文真正流式打字机 | 不支持 | 支持 |
| 按组件局部更新 | 不支持 | 支持 |
| 完成态二次增强 | 很弱 | 强 |
| fallback 简单性 | 强 | 中 |
| 实现复杂度 | 低 | 高 |
| 长期扩展性 | 中 | 高 |

---

## 6. 模块职责设计

## 6.1 `feishu_card_build/` 的职责

建议保留并扩展为：

### 输入
- `response`
- `tools`
- `reasoning`
- `footer` 所需运行信息
- builder config
- `enable_streaming`

### 输出
- `cards`：现有静态卡片输出
- `streaming.initial_card`
- `streaming.streaming_element_id`
- `streaming.streaming_content`
- `streaming.final_mode`（可选）
- `streaming.element_map`（可选）
- `streaming.disable_settings_payload`（可选）

### 需要新增/强化的点
1. 为正文流式组件稳定分配 `element_id`
2. 保证正文第一块流式目标一定是 `markdown` 或 `plain_text`
3. 为完成态保留 footer / tools / reasoning / 正文统一布局
4. 保留现有长度保护，但新增“CardKit 模式下的组件预算”逻辑
5. 保留当前 interactive fallback 所需 `cards`

### 建议新增的 builder 输出契约

```json
{
  "cards": [...],
  "streaming": {
    "enabled": true,
    "initial_card": {...},
    "streaming_element_id": "body_main_1",
    "streaming_content": "完整正文全文",
    "final_cards": [...],
    "element_map": {
      "body_main": "body_main_1",
      "tool_panel": "tool_panel_1",
      "reasoning_panel": "reasoning_panel_1",
      "footer": "footer_1"
    }
  }
}
```

### builder 成功条件

- 无论是否启用 CardKit，都必须产出可回退的 `cards`
- 若 `enable_streaming=true`，则必须保证：
  - `initial_card` 存在
  - `streaming_element_id` 存在
  - `streaming_content` 为非空正文

## 6.2 `run.py.patch` 的职责

1. 判断当前是否启用 CardKit 正式链路
2. 准备 payload 并调用 builder
3. 获取 Feishu access token
4. 创建 card entity
5. 发送 card entity 到会话
6. 执行 streaming text
7. 关闭 streaming mode
8. 必要时做完成态更新
9. 失败时回退到 interactive / 文本

### patch 侧新增模块建议

为了避免 `run.py.patch` 变成一大段不可维护逻辑，建议在工具目录下新增一组辅助模块，再由 patch 调用模块 CLI 或序列化帮助逻辑：

```text
feishu_card_build/
├── cardkit_api.py         # CardKit HTTP 调用封装
├── cardkit_stream.py      # streaming 分段/节流/sequence 逻辑
├── cardkit_payloads.py    # create/update/settings 请求体构造
└── cardkit_config.py      # CardKit 配置解析与默认值
```

> 注意：这些模块仍然位于工具目录中；patch 只负责调用，不把全部实现硬塞进 patch hunks 里。

## 6.3 Feishu Adapter 的职责

优先策略：
- 若 Hermes 现有 Feishu adapter 已可直接发送 `card_id` 形式消息，则复用
- 若不具备，则在 patch 内自行调用消息发送 API

原则：
- 不在 builder 中嵌入任何网络发送逻辑
- 鉴权与请求重试逻辑集中在 gateway patch 一侧

---

## 7. 正式链路的推荐执行流程

### Phase 0：准备期（保持现状）

状态：
- 继续使用 interactive 最终卡片直发
- builder 已可输出 streaming 元信息

本阶段目标：
- 不改默认行为
- 完成 CardKit 发送器设计与测试桩

### Phase 1：新增 CardKit 发送能力（双轨并存）

新增配置，例如：

```yaml
feishu_messaging_card_builder:
  enabled: true
  transport_mode: interactive   # interactive | cardkit
  enable_streaming: false
```

行为：
- `transport_mode=interactive`：保持现状
- `transport_mode=cardkit` 且 `enable_streaming=false`：
  - 创建 card entity
  - 发送 card_id
  - 不做 streaming

本阶段意义：
- 先验证 card entity create/send 基础通路
- 不引入流式复杂度

### Phase 2：接入正文流式输出

新增配置，例如：

```yaml
feishu_messaging_card_builder:
  transport_mode: cardkit
  enable_streaming: true
  streaming_strategy: delay
  streaming_print_step: 1
  streaming_flush_interval_ms: 120
```

行为：
1. builder 生成 `initial_card` + `streaming_content`
2. 创建 card entity
3. 发送 card_id
4. 按节流策略发送 streaming text 更新
5. 文本结束后关闭 `streaming_mode`

注意：
- 不使用 `fast`
- 全正文维持 prefix-append 语义
- sequence 严格递增

### Phase 3：完成态局部更新

在 streaming 完成后：
- 更新 footer 到最终值
- 追加工具/思考面板（如果初始态未完全呈现）
- 追加反馈组件 / 完成标记 / 后续动作按钮

适合使用：
- 卡片级全量更新
- 或组件级局部更新（后续扩展）

### Phase 4：正式链路优先，interactive 退为 fallback

当 CardKit 路径验证足够稳定后：
- 默认模式切到 `cardkit`
- `interactive` 保留为：
  - fallback
  - 简化模式
  - 无 CardKit 权限时的兼容模式

---

## 8. 配置设计建议

建议新增以下配置项：

```yaml
feishu_messaging_card_builder:
  enabled: true

  transport_mode: interactive        # interactive | cardkit
  cardkit_fallback_mode: interactive # interactive | text

  enable_streaming: false
  streaming_print_step: 1
  streaming_print_strategy: delay
  streaming_flush_interval_ms: 120
  streaming_summary_text: 正在生成回答...

  max_card_elements: 180
  max_streaming_buffer_chars: 4000
  max_final_card_chars: 6000

  tool_display_mode: card_panel
  overflow_mode: truncate
```

说明：
- `max_card_elements` 建议低于官方 200，给后续完成态更新留预算
- `streaming_flush_interval_ms` 需要结合 10 次/秒限制
- `cardkit_fallback_mode` 用于控制正式链路失败后的退路

### 建议补充的配置项

```yaml
feishu_messaging_card_builder:
  cardkit_sequence_start: 1
  cardkit_request_timeout_seconds: 15
  cardkit_retry_attempts: 2
  cardkit_retry_backoff_ms: 300
  cardkit_enable_completion_refresh: true
  cardkit_send_mode: adapter_first   # adapter_first | direct_api
```

用途：
- `cardkit_sequence_start`：统一初始化 sequence
- `cardkit_request_timeout_seconds`：控制 OpenAPI 超时
- `cardkit_retry_attempts`：限制失败重试次数
- `cardkit_enable_completion_refresh`：控制是否在结束后再刷一次最终态
- `cardkit_send_mode`：优先走 adapter 还是 patch 自己请求 Feishu 消息发送 API

---

## 9. 关键实现细节

### 9.1 tenant_access_token 获取

CardKit API 明确要求：
- 使用 `tenant_access_token`
- 权限：`cardkit:card:write`

因此 patch 里需要：
1. 读取 Hermes/Feishu 现有 app credentials
2. 若适配器已有 token 获取能力，优先复用
3. 若没有，再在 patch 中补最小可维护实现

### 9.2 card entity 创建

调用：
- `POST /open-apis/cardkit/v1/cards`

请求体使用：
- `type = "card_json"`
- `data = JSON.stringify(initial_card)`

### 9.3 发送 card_id 到会话

发送消息时不再直接发送完整 card JSON，而是发送：
- 基于 `card_id` 的卡片消息

这一步需要审查 Hermes 当前 Feishu adapter 是否已有现成能力；若无，则在 patch 中补标准 API 调用。

### 9.4 正文流式更新

流式对象：
- 首张卡正文主 `markdown` 元素

必须满足：
- 有 `element_id`
- 每次提交的是**全文前缀增长**后的内容
- 保持 `sequence` 严格递增
- 节流到单卡 <= 10 次/秒

### 9.5 关闭流式模式

调用：
- `PATCH /open-apis/cardkit/v1/cards/:card_id/settings`

设置：
- `streaming_mode = false`

### 9.6 完成态增强

可选：
- 将 summary 从“生成中”切到最终摘要
- 更新 footer 为最终 token / provider / model / context 信息
- 补挂反馈区或后续交互组件

### 9.7 sequence 管理规则

建议采用单卡单调递增 sequence：

```text
1  -> create settings / initial state
2  -> first streaming update
3  -> second streaming update
...
N  -> disable streaming
N+1 -> optional completion refresh
```

规则：
- 同一张 card 的所有 CardKit 更新必须严格递增
- 不同 card entity 不共享 sequence 状态
- 任一重试都必须使用新的 sequence，而不是复用已提交值

### 9.8 streaming 文本分片规则

服务端请求层应采用“视觉逐字 + 请求聚合”的双层策略：

1. UI 层参数：
   - `print_step = 1`
   - `print_strategy = delay`
2. 服务端提交层：
   - 每 80~150ms 聚合一次
   - 或当新增字符达到阈值时提交
   - 任一提交都传**最新全文前缀**

### 9.9 streaming 中断后的补偿策略

如果 streaming 在中途失败：

- 若 card entity 已成功发送，则优先尝试：
  1. 关闭 streaming_mode
  2. 再做一次 completion refresh 或整卡 final update
- 若补偿失败，再 fallback 到 interactive 最终卡片
- 若 interactive 也失败，最后 fallback 到原始文本

这样可以避免：
- 用户只看到半截正文
- 卡片一直停留在“生成中”状态

---

## 10. 长度与节流策略

## 10.1 单卡元素预算

官方上限：
- 单卡 200 elements / components

项目建议：
- **内部预算 180**
- 预留至少 20 个组件给：
  - 完成态 footer
  - tools/reasoning 面板
  - 反馈组件
  - 后续补充动作

## 10.2 streaming 文本推送策略

虽然 CardKit 支持流式文本，但不应每生成 1 个字符就立刻请求 API。

建议：
- UI 上配置 `print_step = 1`
- 服务端请求层做缓冲：
  - 按时间窗口聚合，如 80~150ms flush 一次
  - 或按字符增量阈值 flush
- 保证视觉上仍是逐字打印，但 API 调用不超过单卡 10 次/秒

## 10.3 大正文策略

即使 CardKit 的 create/update body 更大，也仍建议：
- builder 保留正文拆卡能力
- streaming 默认仅作用于**首个主正文区块**
- 超长附录、表格、日志片段可：
  - 保持静态
  - 或在完成态作为额外卡片发送

## 10.4 最终态卡片策略

不要把“流式正文 + 全量长工具调用 + 全量思考 + 大表格 + 大 footer”无脑塞进一张完成态卡片。

建议：
- 正文卡优先
- tools/reasoning 作为可折叠区，但仍受组件预算控制
- 超长工具列表允许拆成前置独立卡片
- 表格继续独立组件或独立卡片

## 10.5 fallback 卡片的长度策略

即便进入 CardKit 模式，仍需继续生成当前 `cards`：

- 作为 create/send 失败时的 immediate fallback
- 作为 streaming 中断后的补偿静态卡片
- 作为无 CardKit 权限场景下的兼容输出

因此 builder 的长度保护逻辑**不能因为迁移 CardKit 而删除**，只能按模式增强。

---

## 11. 回退策略

任何正式链路步骤失败时，按以下优先级回退：

### 优先级 1：CardKit 失败 → interactive 最终卡片
适用：
- builder 已成功生成 `cards`
- 只是 card entity / token / update 失败

### 优先级 2：interactive 也失败 → 原始文本
适用：
- 卡片结构被拒绝
- Feishu adapter 交互式发送失败

### 不建议的做法
- 任何 CardKit 中间失败后直接丢失最终答案
- 流式到一半失败后不补发最终完整答复

因此实现上必须保证：
- 有明确 `already_sent` / `partially_sent` 状态机
- 若流式链路中断，仍能补发最终完整静态答复

### 11.1 建议状态机

```text
IDLE
  -> BUILDER_READY
  -> CARD_CREATED
  -> CARD_SENT
  -> STREAMING
  -> STREAMING_DISABLED
  -> COMPLETED
```

异常分支：
- `CARD_CREATED` 前失败：直接 fallback interactive/text
- `CARD_SENT` 后 streaming 失败：补偿关闭 streaming + final refresh
- `STREAMING_DISABLED` 后 completion refresh 失败：保留当前卡片结果即可，不再二次打扰用户

---

## 12. 测试方案

### 12.1 builder 层测试

新增测试覆盖：
1. `build_streaming_card_payload()` 输出：
   - `initial_card`
   - `streaming_element_id`
   - `streaming_content`
2. `streaming_mode=true`
3. `update_multi=true`
4. `print_step=1`
5. `print_strategy=delay`
6. `summary.content` 正确
7. 正文流式目标元素必须带 `element_id`
8. CardKit 模式下仍然保留 `cards` fallback
9. 超长正文在 CardKit 模式下的组件预算不越界

### 12.2 patch 层单测

新增测试覆盖：
1. `transport_mode=interactive` 仍走旧路径
2. `transport_mode=cardkit` 时构造 CardKit payload
3. create/send/settings 请求体字段正确
4. sequence 严格递增
5. 流式结束后关闭 `streaming_mode`
6. 任一步异常时 fallback 到 interactive
7. streaming 中断后会尝试补偿 final refresh

### 12.3 集成测试（dry-run / mock）

建议对外部 HTTP 做 mock：
- create card entity
- send message by card_id
- stream text updates
- disable streaming

验证：
- 顺序正确
- 幂等字段存在
- 错误分支可回退

### 12.4 手工验收

验收重点：
1. 会话里先出现“生成中”卡片
2. 正文确实按逐字打字机效果上屏
3. 结束后停止流式
4. summary 不再停留在“生成中”
5. 工具/思考面板位置正确
6. 超长消息仍能正常拆卡或回退

---

## 13. 文件级改动建议

本节给出后续实施时建议修改的文件范围，便于直接开工。

### 13.1 建议新增文件

```text
/root/feishu_messaging_card_builder/
├── docs/
│   ├── cardkit-formal-migration-plan.md
│   └── cardkit-implementation-checklist.md      # 后续可再新增
└── feishu_card_build/
    ├── cardkit_api.py
    ├── cardkit_stream.py
    ├── cardkit_payloads.py
    └── cardkit_config.py
```

### 13.2 建议修改文件

- `run.py.patch`
  - 接入 transport mode 判断
  - 调用 builder 获取 streaming metadata
  - 调用 CardKit create/send/update/settings
  - fallback 状态机

- `feishu_card_build/builder.py`
  - 稳定输出 `streaming` 元信息
  - CardKit 模式下组件预算控制
  - 完成态结构保留

- `feishu_card_build/cli.py`
  - 输出 `cards + streaming metadata`
  - 明确 dry-run 下的 JSON 契约

- `feishu_card_build/config.py`
  - 新增 CardKit 配置读取

- `config.example.yaml`
  - 增加 `transport_mode` 等示例配置

- `tests/test_feishu_card_build.py`
  - builder / streaming metadata / 长度预算测试

- `tests/test_patch_module_invocation.py`
  - patch 侧 CardKit 调用与 fallback 测试

- `README.md`
  - 增加两种发送模式说明
  - 增加 CardKit 与 interactive 差异说明

---

## 14. 推荐落地顺序

### Milestone 1：文档与接口封装
- 在工具目录中加入本方案文档
- 在 patch 侧新增 CardKit 客户端封装（仅本地可测）

### Milestone 2：card entity create/send 基础链路
- 不开 streaming
- 仅验证正式链路可发最终态卡片

### Milestone 3：正文流式输出
- 接入 `streaming_mode`
- 接入 sequence
- 接入流式节流
- 完成后关闭 streaming

### Milestone 4：完成态增强
- footer 最终刷新
- tools/reasoning 完整展示
- 补充后续交互区

### Milestone 5：默认切换评估
- 比较 CardKit 与 interactive 的稳定性
- 决定是否将默认模式切到 CardKit

---

## 15. 后续实施任务清单（可直接跟着做）

> 这一节是为“后面可以跟着方案走”而写的执行清单。

### Task 1：补配置与契约

**目标**：明确 CardKit 模式的配置与 builder 输出契约。

**文件：**
- Modify: `config.example.yaml`
- Modify: `feishu_card_build/config.py`
- Modify: `feishu_card_build/cli.py`
- Test: `tests/test_feishu_card_build.py`

**完成标准：**
- 配置中支持 `transport_mode` / `enable_streaming` / flush interval / fallback mode
- CLI dry-run 输出稳定 JSON 结构
- 新增单测覆盖配置读取与 streaming 元数据输出

### Task 2：抽离 CardKit 辅助模块

**目标**：避免把全部 HTTP / streaming / payload 逻辑塞进 patch。

**文件：**
- Create: `feishu_card_build/cardkit_api.py`
- Create: `feishu_card_build/cardkit_payloads.py`
- Create: `feishu_card_build/cardkit_stream.py`
- Create: `feishu_card_build/cardkit_config.py`
- Test: `tests/test_cardkit_helpers.py`

**完成标准：**
- create/update/settings 请求体构造与 HTTP 封装可单独测试
- streaming 节流与 sequence 逻辑有独立测试

### Task 3：builder 输出稳定的 streaming payload

**目标**：让 builder 对 CardKit 模式提供稳定输入。

**文件：**
- Modify: `feishu_card_build/builder.py`
- Modify: `feishu_card_build/cli.py`
- Test: `tests/test_feishu_card_build.py`

**完成标准：**
- `initial_card`
- `streaming_element_id`
- `streaming_content`
- `final_cards`
- `element_map`

### Task 4：patch 接入 card entity create/send（无 streaming）

**目标**：先验证最小 CardKit 通路。

**文件：**
- Modify: `run.py.patch`
- Modify: `tests/test_patch_module_invocation.py`

**完成标准：**
- `transport_mode=cardkit` 时走 create/send
- 失败自动 fallback interactive
- 原有 interactive 路径不回归

### Task 5：patch 接入正文 streaming

**目标**：实现逐字视觉效果流式正文。

**文件：**
- Modify: `run.py.patch`
- Modify: `feishu_card_build/cardkit_stream.py`
- Test: `tests/test_patch_module_invocation.py`
- Test: `tests/test_cardkit_helpers.py`

**完成标准：**
- sequence 递增正确
- flush 节流生效
- 使用 `delay`
- `print_step=1`
- 中途失败能补偿或 fallback

### Task 6：接入关闭 streaming 与完成态刷新

**目标**：把卡片从“生成中”正确切到“完成”。

**文件：**
- Modify: `run.py.patch`
- Modify: `feishu_card_build/cardkit_payloads.py`
- Test: `tests/test_patch_module_invocation.py`

**完成标准：**
- 结束后明确关闭 `streaming_mode`
- `summary` 不再显示“生成中”
- footer / tools / reasoning 处于最终态

### Task 7：文档与 README 更新

**目标**：对外说明两条链路、配置差异与 fallback 行为。

**文件：**
- Modify: `README.md`
- Modify: `docs/cardkit-formal-migration-plan.md`
- Optional: `docs/cardkit-implementation-checklist.md`

**完成标准：**
- README 能解释 interactive 与 CardKit 的关系
- docs 中保留实施顺序与权威引用

---

## 16. 实施前检查清单

在真正开工修改代码前，先确认：

- [ ] 当前工具目录测试全绿
- [ ] `run.py.patch` 仍为 unified diff + `patch -p0`
- [ ] builder 当前 `streaming` 元数据输出逻辑可复现
- [ ] 已确认 CardKit 所需权限：`cardkit:card:write`
- [ ] 已确认 token 来源方案（adapter 优先 or patch 直取）
- [ ] 已确认 fallback 到 interactive/text 的状态机方案
- [ ] 已确认 `.gitignore` / README / docs 更新策略

---

## 17. 最终建议

### 建议结论

对 `feishu_messaging_card_builder` 来说，**值得迁移到 CardKit 正式链路**，但应遵循以下策略：

1. **不要一次性推翻当前 interactive 直发链路**
2. **先做双轨并存**
3. **先验证 create/send，再上 streaming**
4. **保留 interactive 与文本 fallback**
5. **继续保留长度保护、组件预算、拆卡和节流机制**

### 一句话总结

> CardKit 的价值不在于“没有长度限制”，而在于它把卡片从“一次性静态消息”升级为“可持续更新的实体资源”，从而为正文流式输出、组件局部更新和完成态演进提供了更稳定、更可扩展的正式基础设施。

---

## 18. 本方案引用的权威文档

1. 卡片 JSON 2.0 结构  
   `https://open.feishu.cn/document/feishu-cards/card-json-v2-structure.md`

2. 流式更新卡片总览  
   `https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/streaming-updates-openapi-overview.md`

3. 飞书卡片资源概述 / CardKit OpenAPI 总览  
   `https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/cardkit-v1/feishu-card-resource-overview.md`

4. 创建卡片实体  
   `https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/cardkit-v1/card/create.md`

5. 全量更新卡片实体  
   `https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/cardkit-v1/card/update.md`

6. 更新卡片配置  
   `https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/cardkit-v1/card/settings.md`

7. 富文本组件（Markdown）  
   `https://open.feishu.cn/document/feishu-cards/card-json-v2-components/content-components/rich-text.md`

8. 普通文本组件  
   `https://open.feishu.cn/document/feishu-cards/card-json-v2-components/content-components/plain-text.md`
