# 项目文档索引

这些文档记录项目方向、研究结论与原型阶段的架构决策。它们不是实施计划，也不要求当前阶段选定所有技术细节。

建议阅读顺序：

1. `project-direction.md`：先理解项目解决的问题、边界和原则。
2. `hermes-research.md`：理解 Hermes 官方能力与它没有覆盖的部分。
3. `feishu-card-research.md`：确认飞书卡片实体、Card JSON v2 约束。
4. `phase-1-prototype-decisions.md`：**[NEW]** Phase 1 原型的架构选择与设计理由。
5. `phase-2-reliability-contract.md`：**[NEW]** Plan 3 冻结的最小可靠性契约，定义状态机、幂等、更新窗口与失败分类。
6. `hermes-outbound-seam-memo.md`：**[NEW]** 确定如何拦截并重定向 Hermes 的出站消息。
7. `phase-3-runtime-bridge-design.md`：**[NEW]** Phase 3 运行时桥接设计冻结备忘录，收敛接缝、事件契约、失败上限与可逆边界。
8. `phase-1-live-validation.md`：**[NEW]** 查看 Phase 1 现场测试的证据与通过标准。
9. `evidence-privacy-taxonomy.md`：**[NEW]** 证据与隐私分类规范，定义 safe/quarantined/invalid 等级。
10. `roadmap.md`：确认长期方向、阶段路线和哪些决策可以延后。
11. `git-standards.md`：确认分支、提交、PR 和历史整理规范。
12. `open-questions.md`：最后整理目前依然悬而未决的问题。
13. `AGENTS.md`：面向代码代理的文档工作规则。

核心结论：Phase 1 & 2 验证了“消息拦截 -> 实体创建 -> 动态更新”链路的技术可行性与可靠性。Phase 3 通过运行时桥接框架（Runtime Bridge Harness）在 mock 环境下收敛了 Hermes 与飞书卡片之间的事件契约，并完成了设计冻结。

当前约束：只考虑 Hermes Feishu/Lark websocket 连接方式；任何对 Hermes 源码或其他非本项目内容的修改，都必须可安装、可卸载、可更新、可审计和可恢复。
