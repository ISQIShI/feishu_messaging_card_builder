# CardKit 正式链路迁移实施清单

> 对应方案文档：`./plan.md`
>
> 使用方式：按顺序逐项完成；每项完成后补测试结果、提交记录和遗留问题。

---

## 0. 基础信息

- 目标分支：`migration/cardkit-formal-chain`
- 合并目标：`dev`
- 主方案文档：`docs/migrations/cardkit-formal-migration/plan.md`
- 当前模式：interactive 最终卡片直发 + fallback 文本
- 目标模式：CardKit 正式链路 + 保留 interactive / 文本 fallback

---

## 1. 开工前检查

- [ ] 当前工作分支正确：`migration/cardkit-formal-chain`
- [ ] `git status` 干净或变更已知
- [ ] 当前测试全绿
- [ ] `run.py.patch` 仍采用 unified diff + `patch -p0`
- [ ] CardKit 所需权限已确认：`cardkit:card:write`
- [ ] 已确认 token 来源策略（adapter 优先 / patch 直取）
- [ ] 已确认 fallback 状态机
- [ ] 已阅读 `plan.md`

建议命令：

```bash
git branch --show-current
git status
python3 -m unittest tests/test_feishu_card_build.py tests/test_package_entrypoints.py tests/test_patch_module_invocation.py tests/test_backup_metadata.py -v
```

---

## 2. Task 1：补配置与契约

**目标**：明确 CardKit 模式配置与 builder 输出契约。

**文件：**
- Modify: `config.example.yaml`
- Modify: `feishu_card_build/config.py`
- Modify: `feishu_card_build/cli.py`
- Test: `tests/test_feishu_card_build.py`

### 待办
- [ ] 增加 `transport_mode`
- [ ] 增加 `cardkit_fallback_mode`
- [ ] 增加 `enable_streaming`
- [ ] 增加 `streaming_flush_interval_ms`
- [ ] 增加 request timeout / retry / send_mode 等配置
- [ ] CLI dry-run 输出稳定 `cards + streaming` 结构
- [ ] 为新配置补测试

### 完成标准
- [ ] 新配置能被解析
- [ ] CLI 输出结构稳定
- [ ] 测试通过

---

## 3. Task 2：抽离 CardKit 辅助模块

**目标**：避免把全部逻辑塞进 patch。

**文件：**
- Create: `feishu_card_build/cardkit_api.py`
- Create: `feishu_card_build/cardkit_payloads.py`
- Create: `feishu_card_build/cardkit_stream.py`
- Create: `feishu_card_build/cardkit_config.py`
- Test: `tests/test_cardkit_helpers.py`

### 待办
- [ ] 封装 create card entity 请求
- [ ] 封装 update card 请求
- [ ] 封装 update settings 请求
- [ ] 封装 sequence 生成逻辑
- [ ] 封装 streaming flush/节流逻辑
- [ ] 增加 helper 层单测

### 完成标准
- [ ] HTTP payload 构造可单测
- [ ] stream 节流逻辑可单测
- [ ] 无需依赖 patch 即可测试核心 helper

---

## 4. Task 3：builder 输出稳定的 streaming payload

**目标**：让 builder 对 CardKit 模式提供稳定输入。

**文件：**
- Modify: `feishu_card_build/builder.py`
- Modify: `feishu_card_build/cli.py`
- Test: `tests/test_feishu_card_build.py`

### 待办
- [ ] 保证 `initial_card` 始终存在
- [ ] 保证 `streaming_element_id` 稳定
- [ ] 保证 `streaming_content` 为完整正文
- [ ] 保留 `cards` 作为 fallback
- [ ] 增加 `final_cards`
- [ ] 增加 `element_map`
- [ ] 增加 CardKit 模式组件预算控制

### 完成标准
- [ ] builder 契约与 `plan.md` 对齐
- [ ] 超长正文不破坏 fallback cards
- [ ] 对应测试通过

---

## 5. Task 4：patch 接入 card entity create/send（无 streaming）

**目标**：先打通最小 CardKit 正式链路。

**文件：**
- Modify: `run.py.patch`
- Modify: `tests/test_patch_module_invocation.py`

### 待办
- [ ] 读取 `transport_mode`
- [ ] 当 `transport_mode=cardkit` 时调用 create card entity
- [ ] 成功后发送 card_id 到会话
- [ ] 失败时 fallback 到 interactive
- [ ] 保持 `transport_mode=interactive` 行为不变

### 完成标准
- [ ] CardKit create/send 能被 mock 验证
- [ ] 原 interactive 路径无回归
- [ ] patch 单测通过

---

## 6. Task 5：patch 接入正文 streaming

**目标**：实现逐字视觉效果流式正文。

**文件：**
- Modify: `run.py.patch`
- Modify: `feishu_card_build/cardkit_stream.py`
- Test: `tests/test_patch_module_invocation.py`
- Test: `tests/test_cardkit_helpers.py`

### 待办
- [ ] 接入 `enable_streaming`
- [ ] 接入 `sequence` 严格递增
- [ ] 接入 flush interval 节流
- [ ] 使用 `delay`
- [ ] 保持 `print_step=1`
- [ ] 失败时执行补偿或 fallback

### 完成标准
- [ ] streaming 请求顺序正确
- [ ] 单卡更新频率不突破约束
- [ ] 中断可恢复或回退

---

## 7. Task 6：关闭 streaming 与完成态刷新

**目标**：从“生成中”切到“完成态”。

**文件：**
- Modify: `run.py.patch`
- Modify: `feishu_card_build/cardkit_payloads.py`
- Test: `tests/test_patch_module_invocation.py`

### 待办
- [ ] 流式完成后关闭 `streaming_mode`
- [ ] 更新 `summary`
- [ ] 更新 footer 到最终态
- [ ] 若需要，刷新 tools/reasoning 完整内容
- [ ] 失败时不重复打扰用户，但保留最终可读结果

### 完成标准
- [ ] 卡片不再停留在“生成中”
- [ ] 完成态布局正确
- [ ] 补偿逻辑可测

---

## 8. Task 7：文档与 README 更新

**目标**：同步说明两种链路和新的 git/迁移规范。

**文件：**
- Modify: `README.md`
- Modify: `docs/migrations/cardkit-formal-migration/plan.md`
- Modify: `docs/git-workflow.md`

### 待办
- [ ] README 增加 interactive vs CardKit 说明
- [ ] README 增加 fallback 说明
- [ ] 迁移文档与代码实现保持一致
- [ ] git 规范文档补充实际分支名

### 完成标准
- [ ] 新人只看 docs 能理解开发流程
- [ ] 文档与代码现状一致

---

## 9. 测试与验收

### 自动化测试
- [ ] `tests/test_feishu_card_build.py`
- [ ] `tests/test_package_entrypoints.py`
- [ ] `tests/test_patch_module_invocation.py`
- [ ] `tests/test_backup_metadata.py`
- [ ] `tests/test_cardkit_helpers.py`（新增后）

建议命令：

```bash
python3 -m unittest \
  tests/test_feishu_card_build.py \
  tests/test_package_entrypoints.py \
  tests/test_patch_module_invocation.py \
  tests/test_backup_metadata.py \
  tests/test_cardkit_helpers.py -v
```

### 手工验收
- [ ] 先出现“生成中”卡片
- [ ] 正文按逐字视觉效果输出
- [ ] 流式结束后关闭 streaming
- [ ] summary 更新正确
- [ ] footer 为最终态
- [ ] tools / reasoning 面板位置正确
- [ ] 超长内容仍能 fallback

---

## 10. 提交与合并

### 分支约束
- 当前开发分支：`migration/cardkit-formal-chain`
- 完成后合并到：`dev`
- 不直接合并到：`main`

### 提交建议
- [ ] 每完成一个 Task 至少一次提交
- [ ] 提交信息清晰，例如：
  - `feat: add cardkit config and payload contract`
  - `feat: add card entity create/send path`
  - `feat: implement cardkit streaming updates`
  - `docs: update migration plan and checklist`

### 合并前检查
- [ ] 分支测试全绿
- [ ] 文档同步更新
- [ ] `git diff dev...HEAD` 可解释
- [ ] fallback 行为已验证

---

## 11. 执行记录

### 当前进度
- [ ] Task 1
- [ ] Task 2
- [ ] Task 3
- [ ] Task 4
- [ ] Task 5
- [ ] Task 6
- [ ] Task 7

### 备注
- 风险：
- 阻塞：
- 待确认事项：
- 手工验证结果：

---

## 12. 完成判定

只有当下面全部满足时，才算本次迁移分支可申请合并到 `dev`：

- [ ] CardKit create/send 通路可用
- [ ] streaming 正文可用
- [ ] streaming 结束后能关闭
- [ ] completion refresh 行为正常
- [ ] fallback 行为正常
- [ ] 测试通过
- [ ] 文档同步完成
- [ ] 分支规范遵守完毕
