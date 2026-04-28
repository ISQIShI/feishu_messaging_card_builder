# 飞书卡片官方资料研究摘要

## 资料范围

本摘要依据飞书开放平台官方文档，重点关注卡片实体、Card JSON v2、发送与更新。

- 创建卡片实体：https://open.feishu.cn/document/cardkit-v1/card/create
- 飞书卡片资源概览：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/cardkit-v1/feishu-card-resource-overview
- 发送飞书卡片：https://open.feishu.cn/document/feishu-cards/send-feishu-card
- 更新飞书卡片：https://open.feishu.cn/document/feishu-cards/update-feishu-card
- Card JSON v2 结构：https://open.feishu.cn/document/feishu-cards/card-json-v2-structure
- Card JSON v2 组件概览：https://open.feishu.cn/document/feishu-cards/card-json-v2-components/component-json-v2-overview
- 更新卡片实体：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/cardkit-v1/card/update

## 核心结论

官方文档支持以卡片实体为中心的方向：创建卡片实体，获取 `card_id`，再通过卡片 ID 发送和更新。直接发送卡片 JSON 仍有文档路径，但更适合一次性消息；如果项目目标包括复用、更新或流式更新，实体路径更符合官方文档的资源模型。

## 相关 API 与资源模型

创建卡片实体使用 `POST /open-apis/cardkit/v1/cards`，返回 `card_id`。创建接口支持 Card JSON 2.0 或新版搭建工具卡片。

完整更新卡片实体使用 `PUT /open-apis/cardkit/v1/cards/:card_id`，按 `card_id` 替换整张卡片，且支持 Card JSON 2.0。

资源概览还列出多种实体级或组件级更新能力，包括卡片设置更新、批量更新、元素创建、元素更新和元素内容更新。这些接口都围绕 `card_id` 运作；涉及组件时还需要稳定的 `element_id`。

发送卡片文档包含通过卡片实体 ID 发送的路径，并说明它适合需要多次更新或流式更新的卡片场景。更新卡片文档则说明卡片发送后仍可在一定窗口内更新。

## Card JSON v2 约束

Card JSON v2 需要声明 `schema: "2.0"`。它不是普通 Markdown 的包装，而是一套结构化卡片模型。

Card JSON v2 单卡最多支持 200 个元素或组件。长回复、工具摘要、表格、附件说明和运行状态都需要考虑这个限制。

Card JSON v2 需要飞书客户端 7.20 及以上版本支持。目标用户环境若包含更老客户端，需要提前确认降级策略。

`config.update_multi` 在 v2 或卡片实体创建路径中应按可共享更新模型理解；创建接口和结构文档对该配置有明确限制。未来不应假设每个接收者都能拥有互不影响的独立卡片状态，除非发送模型和更新模型都经过验证。

`element_id` 必须在卡片内唯一，只能包含字母、数字、下划线，必须以字母开头，最长 20 个字符。若未来支持部分更新或流式更新，组件 ID 需要从内容建模阶段开始稳定设计，不能在渲染时随机生成。

Card JSON v2 组件分为容器类、展示类和交互类。未来内容模型应先决定 Hermes 输出中的段落、代码、表格、状态、操作按钮等分别映射到哪类组件，而不是只做字符串替换。

## 对本项目的含义

本项目的核心资源不应只是“卡片 JSON”，而应是“卡片实体记录”。它至少需要表达：来源消息、目标会话、创建出的 `card_id`、发送状态、可更新窗口、组件 ID 索引、最近一次内容版本和失败状态。

如果项目支持更新，需要提前选择更新粒度：整卡替换、批量更新、组件更新或组件内容更新。粒度越细，对 `element_id` 稳定性和状态存储的要求越高。

如果项目只支持最终回复卡片化，也仍建议使用卡片实体路径，因为这能保留未来扩展到更新、流式展示和交互的空间。

## 不确定点

- **发送路径**: 已解决 (Phase 2 实时验证)。官方路径为 IM 消息，`msg_type: interactive`，内容为 `{"type":"card","data":{"card_id":"..."}}`。证据参考 `.sisyphus/evidence/plan-2/`。
- 需要确认目标环境是否全部满足 Card JSON v2 的飞书客户端版本要求。
- **更新限制**: 已验证 (Phase 2 实时验证)。`sequence` 必须严格递增，否则触发错误 `300317`。
- 需要确认使用 JSON v2 直接建模，还是使用飞书搭建工具生成的新版卡片作为创作入口。
