#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_PY="$HERMES_HOME/hermes-agent/gateway/run.py"
CONFIG_YAML="$HERMES_HOME/config.yaml"
SCRIPT_DIR="$HERMES_HOME/scripts"
TARGET_PACKAGE_DIR="$SCRIPT_DIR/feishu_card_build"
TARGET_MAIN_ENTRY="$TARGET_PACKAGE_DIR/__main__.py"
PATCH_FILE="$PACKAGE_DIR/run.py.patch"
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

失败退出() {
  echo -e "${COLOR_RED}${COLOR_BOLD}安装失败：${COLOR_RESET}$*" >&2
  exit 1
}
提示() { echo -e "${COLOR_CYAN}[飞书消息卡片构建器]${COLOR_RESET} $*"; }
成功() { echo -e "${COLOR_GREEN}[完成]${COLOR_RESET} $*"; }
注意() { echo -e "${COLOR_YELLOW}[提示]${COLOR_RESET} $*"; }
确保备份目录() {
  if [[ "$BACKUP_DIR_CREATED" -eq 0 ]]; then
    mkdir -p "$BACKUP_DIR"
    BACKUP_DIR_CREATED=1
    提示 "备份目录：$BACKUP_DIR"
  fi
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

[[ -f "$RUN_PY" ]] || 失败退出 "未找到 run.py：$RUN_PY"
[[ -f "$PATCH_FILE" ]] || 失败退出 "未找到补丁文件：$PATCH_FILE"
[[ -d "$PACKAGE_DIR/feishu_card_build" ]] || 失败退出 "未找到构建包目录：$PACKAGE_DIR/feishu_card_build"
[[ -f "$PACKAGE_DIR/feishu_card_build/__main__.py" ]] || 失败退出 "未找到包入口：$PACKAGE_DIR/feishu_card_build/__main__.py"
[[ -f "$PACKAGE_DIR/feishu_card_build/cli.py" ]] || 失败退出 "未找到 CLI 模块：$PACKAGE_DIR/feishu_card_build/cli.py"

提示 "第 1/3 步：检查 run.py"
if grep -q "_try_send_feishu_final_card" "$RUN_PY"; then
  失败退出 "检测到当前 run.py 似乎已经打过补丁，已拒绝继续执行"
fi

PATCH_DRY_RUN_OUTPUT="$(mktemp)"
cleanup() { rm -f "$PATCH_DRY_RUN_OUTPUT"; }
trap cleanup EXIT
if ! (
  cd "$HERMES_HOME"
  patch --dry-run -N -p0 < "$PATCH_FILE"
) >"$PATCH_DRY_RUN_OUTPUT" 2>&1; then
  echo -e "${COLOR_YELLOW}补丁预检查输出：${COLOR_RESET}" >&2
  cat "$PATCH_DRY_RUN_OUTPUT" >&2
  失败退出 "当前 run.py 结构不支持干净应用该补丁"
fi

确保备份目录
cp "$RUN_PY" "$BACKUP_DIR/run.py"
成功 "已备份 run.py"
写入元数据 "$BACKUP_DIR/run.py" "install"
(
  cd "$HERMES_HOME"
  patch -N -p0 < "$PATCH_FILE"
)
成功 "已完成 run.py 补丁应用"

mkdir -p "$SCRIPT_DIR"
rm -rf "$TARGET_PACKAGE_DIR"
cp -R "$PACKAGE_DIR/feishu_card_build" "$TARGET_PACKAGE_DIR"
chmod +x "$TARGET_MAIN_ENTRY"
成功 "已安装构建包目录：$TARGET_PACKAGE_DIR"

提示 "第 2/3 步：检查 config.yaml"
python3 - "$CONFIG_YAML" "$BACKUP_DIR" <<'PY'
import sys
from pathlib import Path
try:
    import yaml
except Exception as exc:
    raise SystemExit(f"安装失败：更新 config.yaml 需要 PyYAML：{exc}")
config_path = Path(sys.argv[1])
backup_dir = Path(sys.argv[2])
raw = yaml.safe_load(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
raw = raw or {}
if not isinstance(raw, dict):
    raise SystemExit('安装失败：config.yaml 根节点必须是映射')
if isinstance(raw.get("feishu_messaging_card_builder"), dict):
    print("\u001b[33m[飞书消息卡片构建器]\u001b[0m 检测到 config.yaml 已存在 feishu_messaging_card_builder 配置，跳过配置写入")
    raise SystemExit(0)
backup_dir.mkdir(parents=True, exist_ok=True)
if config_path.exists():
    target_backup = backup_dir / 'config.yaml'
    if not target_backup.exists():
        target_backup.write_text(config_path.read_text(encoding='utf-8'), encoding='utf-8')
        print(f'\u001b[32m[完成]\u001b[0m 已备份 config.yaml：{target_backup}')
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
print('\u001b[32m[完成]\u001b[0m 已写入 feishu_messaging_card_builder 配置')
PY

提示 "第 3/3 步：执行语法校验"
python3 -m py_compile "$RUN_PY" "$TARGET_PACKAGE_DIR"/*.py
成功 "语法校验通过"

echo
echo -e "${COLOR_GREEN}${COLOR_BOLD}安装完成。${COLOR_RESET}请重启 Hermes Gateway 以使配置生效。"
echo -e "${COLOR_YELLOW}如需停用，可将 $CONFIG_YAML 中的 feishu_messaging_card_builder.enabled 设置为 false。${COLOR_RESET}"
if [[ "$BACKUP_DIR_CREATED" -eq 1 ]]; then
  echo -e "${COLOR_CYAN}本次备份目录：$BACKUP_DIR${COLOR_RESET}"
fi
