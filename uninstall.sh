#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
RUN_PY="$HERMES_HOME/hermes-agent/gateway/run.py"
CONFIG_YAML="$HERMES_HOME/config.yaml"
TARGET_PACKAGE_DIR="$HERMES_HOME/scripts/feishu_card_build"
BACKUP_ROOT="$HERMES_HOME/backups"

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

失败退出() { echo -e "${COLOR_RED}${COLOR_BOLD}卸载失败：${COLOR_RESET}$*" >&2; exit 1; }
提示() { echo -e "${COLOR_CYAN}[飞书消息卡片构建器]${COLOR_RESET} $*"; }
成功() { echo -e "${COLOR_GREEN}[完成]${COLOR_RESET} $*"; }
注意() { echo -e "${COLOR_YELLOW}[提示]${COLOR_RESET} $*"; }

[[ -f "$RUN_PY" ]] || 失败退出 "未找到 run.py：$RUN_PY"
LATEST_BACKUP="$(find "$BACKUP_ROOT" -maxdepth 1 -type d -name 'feishu_messaging_card_builder_*' 2>/dev/null | sort | tail -n 1 || true)"
ORIGINAL_RUN_BACKUP="$(python3 - "$LATEST_BACKUP" <<'PY'
import json
import sys
from pathlib import Path
backup_dir = Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else None
if not backup_dir or not backup_dir.exists():
    print("")
    raise SystemExit(0)
meta = backup_dir / 'metadata.json'
if meta.exists():
    try:
        data = json.loads(meta.read_text(encoding='utf-8'))
    except Exception:
        data = {}
    original = data.get('original_run_backup') or ''
    if original:
        print(original)
        raise SystemExit(0)
run_path = backup_dir / 'run.py'
print(str(run_path) if run_path.exists() else "")
PY
)"

提示 "开始卸载"
if [[ -n "$ORIGINAL_RUN_BACKUP" && -f "$ORIGINAL_RUN_BACKUP" ]]; then
  cp "$ORIGINAL_RUN_BACKUP" "$RUN_PY"
  成功 "已从原始备份恢复 run.py：$ORIGINAL_RUN_BACKUP"
elif [[ -n "$LATEST_BACKUP" && -f "$LATEST_BACKUP/run.py" ]]; then
  cp "$LATEST_BACKUP/run.py" "$RUN_PY"
  成功 "已从最近备份恢复 run.py：$LATEST_BACKUP/run.py"
else
  注意 "未找到可用的 run.py 备份，跳过 run.py 恢复"
fi

if [[ -d "$TARGET_PACKAGE_DIR" ]]; then
  rm -rf "$TARGET_PACKAGE_DIR"
  成功 "已删除已安装的构建包目录：$TARGET_PACKAGE_DIR"
else
  注意 "未找到已安装的构建包目录，跳过删除"
fi

python3 - "$CONFIG_YAML" "$LATEST_BACKUP" <<'PY'
import sys
from pathlib import Path
config_path = Path(sys.argv[1])
backup_dir = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
backup_hint = str((backup_dir / 'config.yaml')) if backup_dir else '（无可用备份）'
try:
    import yaml
except Exception as exc:
    print(f'\u001b[33m[提示]\u001b[0m 无法自动处理 config.yaml（缺少 PyYAML：{exc}）。如需手动移除，请参考：{backup_hint}')
    raise SystemExit(0)
if not config_path.exists():
    print('\u001b[33m[提示]\u001b[0m 未找到 config.yaml，跳过配置清理')
    raise SystemExit(0)
try:
    raw = yaml.safe_load(config_path.read_text(encoding='utf-8')) or {}
except Exception as exc:
    print(f'\u001b[33m[提示]\u001b[0m 无法解析 config.yaml：{exc}。请手动移除 feishu_messaging_card_builder；可参考备份：{backup_hint}')
    raise SystemExit(0)
if not isinstance(raw, dict):
    print(f'\u001b[33m[提示]\u001b[0m config.yaml 根节点不是映射，无法自动移除 feishu_messaging_card_builder。请手动处理；可参考备份：{backup_hint}')
    raise SystemExit(0)
builder = raw.get('feishu_messaging_card_builder')
if builder is None:
    print('\u001b[33m[提示]\u001b[0m 未检测到 feishu_messaging_card_builder 配置，跳过配置清理')
    raise SystemExit(0)
if not isinstance(builder, dict):
    print(f'\u001b[33m[提示]\u001b[0m feishu_messaging_card_builder 节点类型不是映射，无法自动移除。请手动处理；可参考备份：{backup_hint}')
    raise SystemExit(0)
raw.pop('feishu_messaging_card_builder', None)
config_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding='utf-8')
print('\u001b[32m[完成]\u001b[0m 已移除 feishu_messaging_card_builder 配置')
PY

python3 -m py_compile "$RUN_PY"
成功 "语法校验通过"

echo
echo -e "${COLOR_GREEN}${COLOR_BOLD}卸载完成。${COLOR_RESET}请重启 Hermes Gateway 以使变更生效。"
if [[ -n "$ORIGINAL_RUN_BACKUP" ]]; then
  echo -e "${COLOR_CYAN}参考原始备份路径：$ORIGINAL_RUN_BACKUP${COLOR_RESET}"
elif [[ -n "$LATEST_BACKUP" ]]; then
  echo -e "${COLOR_CYAN}参考备份目录：$LATEST_BACKUP${COLOR_RESET}"
fi
