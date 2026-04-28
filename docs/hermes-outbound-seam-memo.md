# Hermes Outbound Seam Memo

本文档分析 Hermes (`df51ad7`) 的出站消息路径，并确定 Phase 1 的拦截切入点（Seam）。

## Hermes 源码分析

参考版本: `df51ad797332a547aa9589ee3cb11353f204f8db`

### 1. 飞书出站逻辑 (`gateway/platforms/feishu.py`)

在 `feishu.py` 中，消息发送主要通过平台特定的 `send` 或 `reply` 函数实现。目前的实现倾向于发送文本或富文本（post）消息。

- **Seam Location**: 核心逻辑位于消息渲染并调用飞书 API 之前。
- **Observation**: 目前的消息结构是 text/post centric，缺乏卡片实体的封装抽象。

### 2. 会话管理 (`gateway/session.py`)

`session.py` 负责会话状态的维护和 session key 的生成。

- **Context Identification**: 桥接层可以通过会话上下文识别消息的归属，但 Phase 1 决定保持独立的状态存储，仅引用 Hermes 的消息 ID。

## Preferred Seam Candidate: Websocket Wrapper

Phase 1 的首选方案是 **Websocket Wrapper (Observation-only)**。

- **Approach**: 在 Hermes 进程外，通过包装或代理 websocket 通讯来捕获 Hermes 准备发送给飞书的出站流量。
- **Benefit**: 无需修改 Hermes 源码，符合“外部改动必须可逆”的原则。
- **Nature**: 它是观察导向的。它拦截出站事件，将其转换为卡片实体 API 调用，并抑制原有的文本消息发送（如果可能）。

## Fallback Strategy

如果 Websocket Wrapper 在特定环境下难以实现拦截，降级方案为：

- **Manual Bridge Interface**: 提供一个显式的桥接接口，由另一个观察者进程监控 Hermes 的日志或数据库变更，然后异步发出卡片消息。
- **Dual-Delivery**: 在原型验证阶段，允许原文本消息和新卡片消息同时发出，通过视觉比对验证转换正确性。

## Rejected Alternatives

- **Source Code Patching**: 拒绝在 Phase 1 直接修改 `gateway/platforms/feishu.py`。
- **Decorator Injection**: 拒绝在运行时通过 Python 装饰器动态修改 Hermes 类方法。
- **Webhook Redirection**: 拒绝将飞书 Webhook 流量重定向到桥接层，因为 Webhook 已被明确列为 Phase 1 超出范围。

## 非协商约束

### No Hermes Source Modification
Phase 1 **严禁修改**任何 Hermes 源码文件。所有的转换逻辑必须作为外部组件运行。如果未来阶段证明必须修改 Hermes，则必须产出一份详尽的、可逆的“设计备忘录”，而不是直接提交补丁。

### Webhook Context Only
飞书 Webhook 连接方式在本研究中仅作为官方能力的背景上下文（Background Context）。它被明确列为 **Out of Scope**，不属于 Phase 1 的设计路径，也不应出现在接口定义中。
