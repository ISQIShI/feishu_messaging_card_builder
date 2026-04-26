#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_PY="$HERMES_HOME/hermes-agent/gateway/run.py"
CONFIG_YAML="$HERMES_HOME/config.yaml"
SCRIPT_DIR="$HERMES_HOME/scripts"
TARGET_PACKAGE_DIR="$SCRIPT_DIR/feishu_card_build"
TARGET_MAIN_ENTRY="$TARGET_PACKAGE_DIR/__main__.py"
BACKUP_DIR="$HERMES_HOME/backups/feishu_messaging_card_builder_$(date +%Y%m%d_%H%M%S)"
BACKUP_METADATA="$BACKUP_DIR/metadata.json"
BACKUP_DIR_CREATED=0

if [[ -t 1 ]]; then
  COLOR_RESET='\u001b[0m'
  COLOR_BOLD='\u001b[1m'
  COLOR_GREEN='\u001b[32m'
  COLOR_YELLOW='\u001b[33m'
  COLOR_RED='\u001b[31m'
  COLOR_CYAN='\u001b[36m'
else
  COLOR_RESET=''
  COLOR_BOLD=''
  COLOR_GREEN=''
  COLOR_YELLOW=''
  COLOR_RED=''
  COLOR_CYAN=''
fi

失败退出() { echo -e "${COLOR_RED}${COLOR_BOLD}更新失败：${COLOR_RESET}$*" >&2; exit 1; }
提示() { echo -e "${COLOR_CYAN}[飞书消息卡片构建器]${COLOR_RESET} $*"; }
成功() { echo -e "${COLOR_GREEN}[完成]${COLOR_RESET} $*"; }
确保备份目录() {
  if [[ "$BACKUP_DIR_CREATED" -eq 0 ]]; then mkdir -p "$BACKUP_DIR"; BACKUP_DIR_CREATED=1; 提示 "备份目录：$BACKUP_DIR"; fi
}
写入元数据() {
  python3 - "$BACKUP_METADATA" "$1" "$2" <<'PY'
import json
import sys
from pathlib import Path
meta_path = Path(sys.argv[1])
original_run_backup = sys.argv[2]
source = sys.argv[3]
meta = {
    "source": source,
    "original_run_backup": original_run_backup,
}
meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
PY
}
解析原始备份() {
  python3 - "$HERMES_HOME/backups" <<'PY'
import json
import sys
from pathlib import Path
backup_root = Path(sys.argv[1])
latest = sorted(backup_root.glob('feishu_messaging_card_builder_*'))
if not latest:
    print("")
    raise SystemExit(0)
for candidate in reversed(latest):
    meta = candidate / 'metadata.json'
    if not meta.exists():
        continue
    try:
        data = json.loads(meta.read_text(encoding='utf-8'))
    except Exception:
        continue
    original = data.get('original_run_backup') or ''
    if original:
        print(original)
        raise SystemExit(0)
print("")
PY
}

[[ -f "$RUN_PY" ]] || 失败退出 "未找到 run.py：$RUN_PY"
grep -q "_try_send_feishu_final_card" "$RUN_PY" || 失败退出 "当前环境尚未安装最终卡片补丁，请先执行 install.sh"
grep -q '"-m"' "$RUN_PY" || 失败退出 "当前 run.py 尚未切换到标准模块调用方式，请先修复安装状态后再更新"
grep -q '"feishu_card_build"' "$RUN_PY" || 失败退出 "当前 run.py 尚未引用 feishu_card_build 模块，请先修复安装状态后再更新"
[[ -d "$PACKAGE_DIR/feishu_card_build" ]] || 失败退出 "未找到工具包内的构建包目录 feishu_card_build/"
[[ -f "$PACKAGE_DIR/feishu_card_build/__main__.py" ]] || 失败退出 "未找到工具包内的包入口 feishu_card_build/__main__.py"
[[ -f "$PACKAGE_DIR/feishu_card_build/cli.py" ]] || 失败退出 "未找到工具包内的 CLI 模块 feishu_card_build/cli.py"

提示 "第 1/3 步：备份当前安装状态"
确保备份目录
cp "$RUN_PY" "$BACKUP_DIR/run.py"
成功 "已备份当前 run.py"
ORIGINAL_RUN_BACKUP="$(解析原始备份)"
if [[ -z "$ORIGINAL_RUN_BACKUP" || ! -f "$ORIGINAL_RUN_BACKUP" ]]; then
  失败退出 "未能从历史备份 metadata 中解析到 install 前原始 run.py，请先检查备份链是否完整"
fi
cp "$ORIGINAL_RUN_BACKUP" "$RUN_PY"
成功 "已用 install 前原始 run.py 覆盖目标路径，准备重新应用最新补丁"
if [[ -f "$CONFIG_YAML" ]]; then cp "$CONFIG_YAML" "$BACKUP_DIR/config.yaml"; 成功 "已备份 config.yaml"; fi
if [[ -d "$TARGET_PACKAGE_DIR" ]]; then cp -R "$TARGET_PACKAGE_DIR" "$BACKUP_DIR/feishu_card_build"; 成功 "已备份已安装的构建包目录"; fi
write_metadata_source="update"
写入元数据 "$ORIGINAL_RUN_BACKUP" "$write_metadata_source"

提示 "第 2/3 步：重新应用最新补丁并覆盖更新构建包"
(
  cd "$HERMES_HOME"
  patch -N -p0 < "$PACKAGE_DIR/run.py.patch"
)
成功 "已基于 install 前原始 run.py 重新应用最新补丁"
mkdir -p "$SCRIPT_DIR"
rm -rf "$TARGET_PACKAGE_DIR"
cp -R "$PACKAGE_DIR/feishu_card_build" "$TARGET_PACKAGE_DIR"
chmod +x "$TARGET_MAIN_ENTRY"
成功 "已更新构建包目录：$TARGET_PACKAGE_DIR"

提示 "第 3/3 步：检查配置与语法"
python3 - "$CONFIG_YAML" <<'PY'
import sys
from pathlib import Path
try:
    import yaml
except Exception as exc:
    raise SystemExit(f"更新失败：处理 config.yaml 需要 PyYAML：{exc}")
config_path = Path(sys.argv[1])
if not config_path.exists():
    print('\u001b[33m[提示]\u001b[0m 未找到 config.yaml，跳过配置检查')
    raise SystemExit(0)
raw = yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}
if not isinstance(raw, dict):
    raise SystemExit('更新失败：config.yaml 根节点必须是映射')
if isinstance(raw.get("feishu_messaging_card_builder"), dict):
    print("\u001b[32m[完成]\u001b[0m 已检测到 feishu_messaging_card_builder 配置，无需补写")
    raise SystemExit(0)
raw['feishu_messaging_card_builder'] = {
    'enabled': True,
    'mode': 'final_only',
    'fallback_to_text': True,
    'length_protection': {
        'max_card_text_length': 6000,
        'overflow_mode': 'truncate',
    },
    'tool_display_mode': 'card_panel',
}
config_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding='utf-8')
print('\u001b[32m[完成]\u001b[0m 已补写 feishu_messaging_card_builder 配置')
PY

python3 -m py_compile "$RUN_PY" "$TARGET_PACKAGE_DIR"/*.py
成功 "语法校验通过"

echo
echo -e "${COLOR_GREEN}${COLOR_BOLD}更新完成。${COLOR_RESET}请重启 Hermes Gateway 以使变更生效。"
if [[ "$BACKUP_DIR_CREATED" -eq 1 ]]; then
  echo -e "${COLOR_CYAN}本次备份目录：$BACKUP_DIR${COLOR_RESET}"
fi
