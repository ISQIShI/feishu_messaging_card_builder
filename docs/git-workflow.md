# Git 工作流规范

> 适用项目：`feishu_messaging_card_builder`

---

## 1. 目标

本规范用于约束本项目的 Git 目录结构、忽略策略、分支模型、迁移开发流程与合并路径，避免：

- 演示文件混入源码版本库
- reference 参考实现污染正式源码历史
- 迁移工作直接在主分支上进行
- 文档与实际分支/迁移状态脱节

---

## 2. 目录与纳管规则

### 2.1 纳入 git 的内容

应纳入版本库：

- `feishu_card_build/`
- `tests/`
- `docs/`
- `run.py.patch`
- `install.sh / update.sh / check.sh / uninstall.sh`
- `README.md`
- `LICENSE`
- `config.example.yaml`
- 其他正式源码与正式文档

### 2.2 不纳入 git 的内容

以下目录或文件不应纳入版本库：

- `examples/`
- `reference/`
- `__pycache__/`
- `*.pyc`
- `tests/tmp_payload*.json`
- 本地日志、IDE 配置等

### 2.3 演示文件规则

演示文件统一放在：

```text
examples/
```

例如当前演示资产位于：

```text
examples/assets/
```

这些文件用于：
- 本地演示
- 手工验证
- 文档辅助说明

但默认**不进入 git 历史**。

### 2.4 reference 目录规则

`reference/` 用于：
- 存放参考实现
- 对照研究
- 历史样例

它是开发参考资料，不是本项目的正式可维护源码来源，因此默认：
- **保留在工作目录中**
- **排除在 git 版本库之外**

---

## 3. 分支模型

本项目采用三层分支模型：

### 3.1 `main`
用途：
- 对外稳定主分支
- 仅接收已经整理好的阶段性成果

规则：
- 不直接在 `main` 上开发
- 不把未完成迁移直接合并到 `main`

### 3.2 `dev`
用途：
- 日常集成分支
- 迁移、重构、增强功能完成后的合并目标

规则：
- 新特性先合并到 `dev`
- `dev` 稳定后再择机合并到 `main`

### 3.3 主题分支 / 迁移分支
用途：
- 承载单次迁移、重构或专项开发

命名规则建议：

```text
migration/<topic>
feat/<topic>
fix/<topic>
```

本次迁移专用分支固定为：

```text
migration/cardkit-formal-chain
```

规则：
- 从 `dev` 拉出
- 全部迁移工作只在该分支进行
- 完成后合并回 `dev`
- 不直接合并到 `main`

---

## 4. 本项目当前约定分支

当前分支规范如下：

- 稳定主分支：`main`
- 集成分支：`dev`
- 本次迁移分支：`migration/cardkit-formal-chain`

流程：

```text
main
  └── dev
        └── migration/cardkit-formal-chain
```

合并方向：

```text
migration/cardkit-formal-chain -> dev -> main
```

---

## 5. 新任务的分支流程

### 5.1 开始新迁移/新特性前

1. 先切到 `dev`
2. 拉取最新 `dev`
3. 从 `dev` 创建主题分支

示例：

```bash
git checkout dev
git pull --ff-only origin dev
git checkout -b migration/cardkit-formal-chain
```

### 5.2 开发过程中

- 小步提交
- 文档同步更新
- 不把临时调试文件纳入版本库
- 每完成一个阶段至少跑一次测试

### 5.3 完成后

1. 在主题分支自测
2. 将主题分支推送到远程
3. 合并到 `dev`
4. 验证 `dev`
5. 再决定是否从 `dev` 合并到 `main`

---

## 6. 文档与分支联动规则

### 6.1 迁移文档位置

与迁移分支对应的文档，应放在：

```text
docs/migrations/<migration-topic>/
```

本次迁移对应：

```text
docs/migrations/cardkit-formal-migration/
├── plan.md
└── checklist.md
```

### 6.2 文档职责

- `plan.md`：正式设计与迁移方案
- `checklist.md`：实施清单与验收项

### 6.3 文档更新规则

如果迁移分支实现发生变化：
- 文档必须同步更新
- 文档不能长期落后于代码

如果文档与代码不一致：
- 先修正文档或代码，再继续推进

---

## 7. 提交规范

建议使用清晰前缀：

- `feat:` 新功能
- `fix:` 修复
- `refactor:` 重构
- `docs:` 文档
- `test:` 测试
- `chore:` 杂项维护

示例：

```text
feat: add cardkit config and payload contract
feat: implement card entity create and send path
afeat: add cardkit streaming update flow
docs: add migration plan and checklist
test: cover cardkit fallback and sequence handling
```

> 注意：提交信息里避免模糊表述，如 `update`、`fix stuff`、`misc`。

---

## 8. 重新初始化仓库时的规则

如果由于忽略策略、目录结构或历史整理需要重新初始化 Git 仓库：

1. 先完成目录重构
2. 先确认 `.gitignore` 正确
3. 再删除 `.git` 并重新初始化
4. 重建 remote
5. 首次提交只纳入应受控内容
6. 然后再重建 `dev` 和迁移分支

适用场景：
- 大量本不该入库的文件已进入历史
- 目录结构从“实验状态”切换为“正式维护状态”
- 需要干净地重新建立源码边界

---

## 9. 合并规范

### 9.1 主题分支合并到 `dev` 前

必须确认：

- 测试通过
- 文档同步
- fallback 行为可解释
- `git diff dev...HEAD` 可审查

### 9.2 `dev` 合并到 `main` 前

必须确认：

- `dev` 已稳定
- 无明显未完成迁移项
- 文档与 README 已同步
- 如有必要，补 release note

---

## 10. 当前应遵守的实际操作规则

对本项目，当前默认规则是：

1. 演示文件一律放 `examples/`，且不纳入 git
2. `reference/` 不纳入 git
3. 正式开发不在 `main` 上进行
4. 迁移相关开发统一在：
   - `migration/cardkit-formal-chain`
5. 本次迁移最终合并目标是：
   - `dev`
6. 等 `dev` 稳定后，再考虑进入 `main`

---

## 11. 快速命令参考

### 初始化分支模型

```bash
git checkout -b dev
git push -u origin dev
git checkout -b migration/cardkit-formal-chain
git push -u origin migration/cardkit-formal-chain
```

### 查看当前状态

```bash
git branch --show-current
git status
git branch -a
```

### 合并迁移分支到 dev

```bash
git checkout dev
git merge --no-ff migration/cardkit-formal-chain
git push origin dev
```

---

## 12. 一句话总结

> 本项目的 Git 规则是：**正式源码入库，examples/reference 出库；main 保持稳定，dev 做集成，迁移一律在独立 migration 分支完成，再合并回 dev。**
