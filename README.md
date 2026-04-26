# 飞书消息卡片构建器

这是一个面向 Hermes Gateway 的小型补丁包，用来把 **飞书中的最终回复** 改造成 **交互式卡片**。它不会改动 Hermes 的模型调用链，也不会接管工具调用消息；它只在“最终总结即将发出”的那一刻插入一个可回退的卡片发送分支。

如果卡片发送成功，用户看到的是更适合阅读和汇报的卡片结果；如果卡片发送失败，Hermes 会继续走原本的文本发送路径，尽量不影响对话可用性。

---

## 这个工具包能做什么

启用后，飞书侧的最终回复会具备以下特点：

- 最终回复显示为飞书交互式卡片
- **不再使用顶部标题栏**，避免重复占位与视觉噪音
- 正文会保留经过预处理后的、更加适合飞书卡片展示的结构化文本内容
- 底部附带运行信息，例如：
  - 响应耗时
  - 使用模型
  - API 调用次数
  - 上下文占用比例与进度条
- 长回复会自动拆分为多张卡片
- 卡片失败时自动退回原始文本回复

同时，以下行为保持不变：

- 工具调用消息仍按 Hermes 原逻辑独立发送
- 过程性提示消息仍按 Hermes 原逻辑发送
- 审批、媒体发送、记忆系统等原有流程不被接管

---

## 目录结构

```text
feishu_messaging_card_builder/
├── install.sh
├── check.sh
├── update.sh
├── uninstall.sh
├── run.py.patch
├── feishu_card_build/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── builder.py
│   ├── config.py
│   ├── content.py
│   ├── feishu_elements.py
│   ├── footer.py
│   └── parsing.py
├── tests/
│   ├── test_feishu_card_build.py
│   ├── test_package_entrypoints.py
│   ├── test_patch_module_invocation.py
│   └── test_backup_metadata.py
├── config.example.yaml
├── reference/
└── README.md
```

各文件用途如下：

- `install.sh`：安装脚本。负责检测、备份、打补丁、复制构建包目录、写入配置、执行语法校验。
- `check.sh`：检测脚本。用于检查当前 Hermes 环境是否已安装、备份是否存在、补丁状态是否正常。
- `update.sh`：更新脚本。用于在已安装状态下同步最新构建包目录，并基于 install 前的原始 `run.py` 重新应用最新补丁。
- `uninstall.sh`：卸载脚本。用于恢复 `run.py`、删除已安装构建包目录，并优先尝试仅移除 `feishu_messaging_card_builder` 配置。
- `run.py.patch`：对 Hermes `gateway/run.py` 的补丁。
- `feishu_card_build/`：卡片构建 Python 包目录，采用标准包入口结构。
- `tests/test_feishu_card_build.py`：验证无标题栏卡片与 `lark_md` footer 的构建行为。
- `tests/test_package_entrypoints.py`：验证 `python -m feishu_card_build` 可用，且旧兼容入口已移除。
- `tests/test_patch_module_invocation.py`：验证补丁已改为模块调用方式。
- `tests/test_backup_metadata.py`：验证 install / update / uninstall 的原始 `run.py` 备份链语义。
- `config.example.yaml`：配置示例。
- `reference/`：飞书卡片参考实现与文档，用于辅助设计与优化。

---

## 设计说明

### 1）去除顶部标题栏

当前卡片已去除 `header` 顶部标题栏。

这样做的原因是：

- 顶部标题栏会与正文首行标题信息重复
- 长回复分片时，标题栏会造成额外视觉噪音
- 在汇报式卡片里，正文首部结构通常已足够承担标题语义

因此当前卡片结构统一为：

- `schema: 2.0`
- `config`
- `body.elements`

而不再包含 `header`

### 2）footer 改回 `lark_md` 思路

footer 现在不再使用 `note`，也不再简单回退成普通正文 markdown，而是使用更接近原始设计思路的：

- `div`
- `text.tag = lark_md`

即 footer 结构更接近飞书原生说明区风格。

### 3）备份链与回滚语义重构

为了解决“update 之后最新备份目录里保存的是已经 patch 过的 `run.py`，导致 uninstall 无法回退到 install 前原始版本”的问题，当前脚本已经引入：

- `metadata.json`

其核心字段：

- `source`：当前备份是 install 还是 update 生成
- `original_run_backup`：install 前原始 `run.py` 的真实备份路径

这样实现后：

- **install** 时会记录 install 前原始 `run.py` 路径
- **update** 时会继承这条原始路径，并同时保存一份 install 前原始 `run.py` 副本到当前备份目录
- **uninstall** 时优先按 `metadata.json` 中的 `original_run_backup` 回退

最终效果就是：

- uninstall 会尽量回退到 install 之前的原始 `run.py`
- update 不会破坏原始备份链
- 输出给用户的备份路径也更有语义依据

---

## 工作原理

整个方案的关键点只有两个：

### 1）在最终回复出口插入卡片发送逻辑

补丁会修改 Hermes 的：

- `~/.hermes/hermes-agent/gateway/run.py`

当满足以下条件时，会尝试走卡片发送分支：

- 当前平台是 Feishu
- 最终回复内容存在
- 当前回复不是失败结果
- 当前回复没有被原有 streaming 机制提前完整发出
- `feishu_messaging_card_builder.enabled` 已启用

如果卡片发送成功，则跳过原始最终文本发送；如果失败，则继续按 Hermes 的原有文本逻辑发送。

### 2）卡片构建与消息发送分离

`feishu_card_build/` 只做一件事：

- 读取临时 JSON 载荷
- 生成一张或多张飞书交互式卡片 JSON

它不会自己去调用飞书接口。真正的发送动作，仍然复用 Hermes 当前的 FeishuAdapter。这样做的好处是：

- 不额外引入一套飞书鉴权逻辑
- 不需要在工具包中保存飞书密钥
- 发送失败时可以自然回退到 Hermes 现有路径

---

## 文本预处理与飞书卡片适配

飞书交互式卡片并不是标准 Markdown 渲染器，因此像这些常见语法通常不能稳定按原样展示：

- `##` / `###` 级标题
- 复杂嵌套列表与缩进层级
- 一些 HTML 样式标签
- 很长的补充信息块直接平铺展示

当前版本的处理策略做了增强：

- 移除 `MEDIA:` 指令，避免它们污染卡片正文
- 识别 Hermes 状态、思考过程、工具调用、Footer 标记
- 标题保留在正文首部，不再占用顶部标题栏
- Markdown 表格优先转为原生 `table`
- 思考过程与工具调用转换为可折叠面板
- Footer 转为 `lark_md` 说明块
- 在正文分片后，仅最后一张卡片承载 reasoning/tools/footer，避免重复噪音

这样做的目标不是完整还原标准 Markdown，而是让最终卡片在飞书里更稳定、更易读、更接近结构化展示效果。

---

## 媒体资源支持现状

### 当前支持什么

**当前卡片构建逻辑本身不直接把图片、视频、音频嵌进卡片正文。**

从当前代码看，构建阶段会先把类似下面这种媒体指令清掉：

```text
MEDIA:/path/to/file
```

也就是说：

- 如果回复正文里包含 `MEDIA:` 指令
- 卡片构建时会把它移除，不渲染进卡片内容

### 为什么这样设计

因为当前方案采用的是：

- **卡片负责最终结构化文本展示**
- **媒体仍走 Hermes 原有媒体投递链路**

所以现状可以概括为：

- **图片/音频/其他 `MEDIA:` 资源：支持发送，但不是嵌入卡片内部，而是走原有媒体投递流程单独发送**
- **视频：当前卡片构建器没有专门的卡片内视频元素实现**
- **卡片正文内嵌图片/视频：当前不支持**

---

## 安装逻辑说明

当前版本的 `install.sh` 已按照“先检测、再备份、后写入”的顺序改造完成。

### 第一部分：处理 run.py

安装脚本会先检查：

- 目标 `run.py` 是否存在
- 当前 `run.py` 是否已经被打过补丁
- 当前 `run.py` 是否还能被 `run.py.patch` 干净应用

只有在以上检查通过后，才会执行：

1. 备份 `run.py`
2. 写入 `metadata.json`，记录 install 前原始 `run.py` 的路径
3. 应用补丁
4. 将 `feishu_card_build/` 整个目录覆盖复制到：
   - `~/.hermes/scripts/feishu_card_build/`

如果检测失败，脚本会直接停止，不会继续修改文件。

### 第二部分：处理 config.yaml

脚本会先检查是否已经存在：

- `feishu_messaging_card_builder`

如果配置已经存在，则：

- 输出“跳过配置写入”的提示
- 不再重复覆盖配置

如果配置不存在，则：

1. 备份 `config.yaml`
2. 增量写入配置

### 第三部分：执行校验

最后脚本会继续执行原有的剩余逻辑：

- 使用 `py_compile` 对目标 `run.py` 以及 `feishu_card_build/*.py` 做语法校验
- 输出安装完成提示

---

## 更新逻辑说明

`update.sh` 已按“以 install 前原始 `run.py` 为真实基线重新生成 patched 版本”的方式改造。

当前流程是：

1. 备份当前已 patch 的 `run.py`
2. 从历史 metadata 链中找到 install 前原始 `run.py`
3. 把该原始版本复制到本次备份目录中
4. 用这份原始版本重新覆盖目标 `run.py`
5. 再应用最新 patch
6. 覆盖更新构建包目录

这样可以避免：

- update 一次次叠加在已 patch 版本之上
- uninstall 最终只能回到某次 update 前的 patched run.py

---

## 卸载逻辑说明

当前 `uninstall.sh` 的目标是：

- **优先恢复 install 前原始 `run.py`**

具体策略：

1. 读取最新备份目录中的 `metadata.json`
2. 查找其中记录的 `original_run_backup`
3. 若该路径存在，则优先恢复该原始版本
4. 否则回退到最近备份目录中的 `run.py`

因此最终期望已经与现在脚本语义对齐：

- uninstall 最终会尽量正确回退到 install 前的原始 `run.py`
- 输出给用户的参考路径也会优先指向原始备份路径

---

## 安装方法

在工具包目录内执行：

```bash
cd /root/feishu_messaging_card_builder
chmod +x install.sh
./install.sh
```

如果你的 Hermes 不是默认路径，可以指定：

```bash
HERMES_HOME=/你的/.hermes目录 ./install.sh
```

### 直接更新

如果当前环境已经安装过这套补丁，可以直接执行：

```bash
cd /root/feishu_messaging_card_builder
chmod +x update.sh
./update.sh
```

`update.sh` 适用于“当前环境已经安装，想直接同步最新脚本与配置检查逻辑”的场景。它会：

1. 先确认当前环境已经处于已安装状态
2. 备份当前 patched `run.py`、`config.yaml` 与已安装构建包目录
3. 继承并保存 install 前原始 `run.py` 的引用与副本
4. 基于 install 前原始 `run.py` 重新应用最新 patch
5. 覆盖更新 `~/.hermes/scripts/feishu_card_build/`
6. 检查 `feishu_messaging_card_builder` 配置，不存在时自动补写
7. 执行语法校验

---

## 配置示例

```yaml
feishu_messaging_card_builder:
  enabled: true
  mode: final_only
  fallback_to_text: true
```

字段说明：

- `enabled`：是否启用飞书最终回复卡片
- `mode`：当前设计为 `final_only`，表示只接管最终回复
- `fallback_to_text`：当卡片失败时，是否允许继续回退为文本

---

## 与流式输出的关系

启用该方案后，**飞书最终文本 streaming 会被关闭**。

原因很简单：卡片适合“最终一次性展示”，不适合先流式吐出一条文本、最后再补一张卡片，否则用户会看到重复结果。

这并不意味着所有流式/过程消息都消失了。实际行为是：

- 工具调用消息：继续独立发送
- 过程性提示消息：继续独立发送
- 最终总结：改为卡片发送
- 卡片失败：回退普通文本

---

## 如何检查当前安装状态

执行：

```bash
cd /root/feishu_messaging_card_builder
chmod +x check.sh
./check.sh
```

`check.sh` 会检查以下内容：

- 工具包文件是否完整
- `feishu_card_build/` 构建包目录是否存在
- 包内关键文件是否完整
- Hermes 的 `run.py` / `config.yaml` 是否存在
- `~/.hermes/scripts/feishu_card_build/` 是否已安装
- 已安装目录中的标准入口 `__main__.py` 是否存在
- 已安装目录中是否仍残留旧兼容入口痕迹
- `run.py` 是否已包含补丁逻辑
- `run.py` 当前是否已切换到标准模块调用方式
- 补丁 dry-run 的状态
- 最近备份目录是否存在 `metadata.json`
- `metadata.json` 中是否记录了 `original_run_backup`
- `feishu_messaging_card_builder` 配置是否存在
- `install.sh` / `update.sh` / `check.sh` / `uninstall.sh` / `feishu_card_build/*.py` 的语法与编译状态

---

## 测试方法

当前项目包含四组基于 `unittest` 的回归测试：

```bash
cd /root/feishu_messaging_card_builder
python3 -m unittest \
  tests/test_feishu_card_build.py \
  tests/test_package_entrypoints.py \
  tests/test_patch_module_invocation.py \
  tests/test_backup_metadata.py -v
```

当前覆盖的核心行为包括：

- 无顶部标题栏的 Schema 2.0 卡片
- `lark_md` footer
- Markdown 表格转原生 `table`
- Hermes reasoning / tools / footer 标记提取
- `MEDIA:` 指令清理
- 长文本自动分片
- `python3 -m feishu_card_build` 可用
- 旧兼容入口已移除
- `run.py.patch` 已改为模块调用
- install / update / uninstall 的原始 `run.py` 备份链语义

---

## 回滚与停用

### 临时停用

如果只是想停用功能，最简单的方式是把配置改为：

```yaml
feishu_messaging_card_builder:
  enabled: false
```

### 卸载

可以直接执行：

```bash
cd /root/feishu_messaging_card_builder
chmod +x uninstall.sh
./uninstall.sh
```

卸载脚本会：

1. 优先从 `metadata.json` 记录的 install 前原始 `run.py` 恢复
2. 删除已安装的 `~/.hermes/scripts/feishu_card_build/`
3. **优先尝试仅移除 `config.yaml` 中的 `feishu_messaging_card_builder`**
4. 如果 `config.yaml` 结构异常、无法安全自动移除，则输出提示，要求你手动处理，并给出可参考的备份路径

### 备份目录位置

安装、更新时会把备份放到类似目录：

```bash
~/.hermes/backups/feishu_messaging_card_builder_时间戳/
```

目录中常见内容包括：

- `run.py`：本轮操作前的 `run.py`
- `original_run.py`：install 前原始 `run.py` 的副本（update 场景）
- `config.yaml`
- `feishu_card_build/`
- `metadata.json`

---

## 已知限制

这个方案目前仍然是“低侵入补丁”，不是 Hermes 官方插件接口，因此有一些边界需要接受：

1. 它依赖当前 Hermes `gateway/run.py` 的结构；如果上游改动太大，补丁可能无法应用。
2. 飞书卡片对 Markdown 的支持和普通 Markdown 不完全一致；某些复杂表格、HTML 或特殊格式可能显示不理想。
3. 当前方案只负责“最终卡片发送”，并不是“同一张卡片实时更新”。
4. Hermes 升级后如果覆盖了 `run.py`，通常需要重新应用补丁。
5. 当前媒体资源采用“卡片文本 + 媒体单独发送”的模式，而不是卡片内嵌富媒体模式。

---

## 原始项目来源、文档与作者说明

本工具包并非从零重新发明，而是基于原有的飞书卡片补丁方案整理、重命名和重新包装而来。当前版本的目录命名、脚本命名、安装逻辑、检测逻辑与中文化说明，均是在原始方案基础上的再加工。

当前这个工具包是在原始方案基础上，继续做了：
- 目录迁移与重命名
- 原始发送逻辑演化为独立构建包
- 安装逻辑分阶段改造
- 新增 `check.sh`
- 新增 `update.sh`
- 新增 `uninstall.sh`
- 全量中文化提示文本
- 将构建逻辑从单脚本拆分为模块目录
- 引入标准包入口 `__main__.py` 与独立 `cli.py`
- 删除旧兼容入口
- 将 `run.py.patch` 升级为 `python -m feishu_card_build` 标准模块调用
- footer 改回 `lark_md` 风格
- 去除顶部标题栏
- 引入 `metadata.json` 维护原始 `run.py` 备份链
