#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_PY="$HERMES_HOME/hermes-agent/gateway/run.py"
CONFIG_YAML="$HERMES_HOME/config.yaml"
TARGET_PACKAGE_DIR="$HERMES_HOME/scripts/feishu_card_build"
TARGET_MAIN_ENTRY="$TARGET_PACKAGE_DIR/__main__.py"
PATCH_FILE="$PACKAGE_DIR/run.py.patch"
STATUS_OK=1

if [[ -t 1 ]]; then
  COLOR_RESET='\033[0m'
  COLOR_BOLD='\033[1m'
  COLOR_GREEN='\033[32m'
  COLOR_YELLOW='\033[33m'
  COLOR_RED='\033[31m'
  COLOR_CYAN='\033[36m'
else
  COLOR_RESET=''
  COLOR_BOLD=''
  COLOR_GREEN=''
  COLOR_YELLOW=''
  COLOR_RED=''
  COLOR_CYAN=''
fi

分组() { echo; echo -e "${COLOR_BOLD}${COLOR_CYAN}== $* ==${COLOR_RESET}"; }
正常() { echo -e "${COLOR_GREEN}[正常]${COLOR_RESET} $*"; }
注意() { echo -e "${COLOR_YELLOW}[注意]${COLOR_RESET} $*"; STATUS_OK=0; }
异常() { echo -e "${COLOR_RED}[异常]${COLOR_RESET} $*"; STATUS_OK=0; }

分组 "工具包文件"
for rel in README.md install.sh update.sh check.sh uninstall.sh run.py.patch config.example.yaml; do
  [[ -f "$PACKAGE_DIR/$rel" ]] && 正常 "$rel 已存在" || 异常 "$rel 缺失"
done
[[ -d "$PACKAGE_DIR/feishu_card_build" ]] && 正常 "feishu_card_build/ 构建包目录已存在" || 异常 "feishu_card_build/ 构建包目录缺失"
for rel in __init__.py __main__.py cli.py builder.py config.py content.py feishu_elements.py footer.py parsing.py; do
  [[ -f "$PACKAGE_DIR/feishu_card_build/$rel" ]] && 正常 "feishu_card_build/$rel 已存在" || 异常 "feishu_card_build/$rel 缺失"
done
[[ ! -f "$PACKAGE_DIR/feishu_card_build/feishu_card_build.py" ]] && 正常 "旧兼容入口已移除" || 异常 "旧兼容入口仍存在"

分组 "Hermes 目标文件"
[[ -f "$RUN_PY" ]] && 正常 "已找到 run.py：$RUN_PY" || 异常 "未找到 run.py：$RUN_PY"
[[ -f "$CONFIG_YAML" ]] && 正常 "已找到 config.yaml：$CONFIG_YAML" || 注意 "未找到 config.yaml：$CONFIG_YAML"
if [[ -d "$TARGET_PACKAGE_DIR" ]]; then
  正常 "已找到已安装的构建包目录：$TARGET_PACKAGE_DIR"
  if [[ -f "$TARGET_MAIN_ENTRY" ]]; then
    正常 "构建包内标准入口已存在：$TARGET_MAIN_ENTRY"
    [[ -x "$TARGET_MAIN_ENTRY" ]] && 正常 "构建包内标准入口具有可执行权限" || 注意 "构建包内标准入口没有可执行权限"
  else
    异常 "构建包目录存在，但缺少标准入口：$TARGET_MAIN_ENTRY"
  fi
  [[ ! -f "$TARGET_PACKAGE_DIR/feishu_card_build.py" ]] && 正常 "已安装目录中不再包含旧兼容入口" || 异常 "已安装目录中仍存在旧兼容入口"
else
  注意 "尚未找到已安装的构建包目录：$TARGET_PACKAGE_DIR"
fi

分组 "run.py 补丁状态"
if [[ -f "$RUN_PY" ]]; then
  grep -q "_try_send_feishu_final_card" "$RUN_PY" && 正常 "run.py 已包含最终卡片发送钩子" || 注意 "run.py 尚未包含最终卡片发送钩子"
  grep -q '"-m"' "$RUN_PY" && 正常 "run.py 已切换到标准模块调用方式" || 注意 "run.py 尚未切换到标准模块调用方式"
  grep -q '"feishu_card_build"' "$RUN_PY" && 正常 "run.py 已引用 feishu_card_build 模块" || 注意 "run.py 尚未引用 feishu_card_build 模块"
fi

if [[ -f "$RUN_PY" && -f "$PATCH_FILE" ]]; then
  DRY_RUN_OUTPUT="$(mktemp)"
  trap 'rm -f "$DRY_RUN_OUTPUT"' EXIT
  if (
    cd "$HERMES_HOME"
    patch --dry-run -N -p0 < "$PATCH_FILE"
  ) >"$DRY_RUN_OUTPUT" 2>&1; then
    注意 "补丁 dry-run 可以直接通过：这通常表示补丁尚未安装，或当前目标仍处于原始状态"
  else
    if grep -qiE "Reversed \(or previously applied\) patch detected|previously applied" "$DRY_RUN_OUTPUT"; then
      正常 "补丁 dry-run 提示补丁已安装"
    else
      注意 "补丁 dry-run 失败，且原因不是“已安装”；当前 run.py 可能与补丁不兼容"
      cat "$DRY_RUN_OUTPUT"
    fi
  fi
fi

if [[ -f "$RUN_PY" && -d "$TARGET_PACKAGE_DIR" ]] && grep -q "_try_send_feishu_final_card" "$RUN_PY"; then
  分组 "备份检查"
  LATEST_BACKUP="$(find "$HERMES_HOME/backups" -maxdepth 1 -type d -name 'feishu_messaging_card_builder_*' 2>/dev/null | sort | tail -n 1 || true)"
  if [[ -z "$LATEST_BACKUP" ]]; then
    注意 "当前环境看起来已安装，但未找到任何备份目录"
  else
    正常 "已找到最近一次备份目录：$LATEST_BACKUP"
    [[ -f "$LATEST_BACKUP/run.py" ]] && 正常 "备份目录中包含当前轮 run.py 备份" || 注意 "备份目录中缺少当前轮 run.py 备份"
    [[ -f "$LATEST_BACKUP/config.yaml" ]] && 正常 "备份目录中包含 config.yaml" || 注意 "备份目录中未包含 config.yaml（可能是当时配置已存在而跳过备份）"
    if [[ -f "$LATEST_BACKUP/metadata.json" ]]; then
      正常 "备份目录中包含 metadata.json"
      python3 - "$LATEST_BACKUP/metadata.json" <<'PY'
import json
import sys
from pathlib import Path
meta_path = Path(sys.argv[1])
try:
    data = json.loads(meta_path.read_text(encoding='utf-8'))
except Exception as exc:
    print(f'\033[31m[异常]\033[0m metadata.json 无法解析：{exc}')
    raise SystemExit(0)
original = data.get('original_run_backup')
source = data.get('source')
if original:
    print(f'\033[32m[正常]\033[0m original_run_backup: {original}')
else:
    print('\033[33m[注意]\033[0m metadata.json 中未记录 original_run_backup')
if source:
    print(f'\033[32m[正常]\033[0m source: {source}')
else:
    print('\033[33m[注意]\033[0m metadata.json 中未记录 source')
PY
    else
      注意 "备份目录中缺少 metadata.json，卸载时可能无法回退到 install 前原始 run.py"
    fi
  fi
fi

分组 "配置状态"
python3 - "$CONFIG_YAML" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
Y='\033[33m'; R='\033[31m'; G='\033[32m'; Z='\033[0m'
if not path.exists():
    print(f'{Y}[注意]{Z} 未找到 config.yaml，无法检查 feishu_messaging_card_builder 配置')
    raise SystemExit(0)
try:
    import yaml
except Exception as exc:
    print(f'{R}[异常]{Z} 无法导入 PyYAML：{exc}')
    raise SystemExit(0)
try:
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
except Exception as exc:
    print(f'{R}[异常]{Z} 无法解析 config.yaml：{exc}')
    raise SystemExit(0)
if not isinstance(data, dict):
    print(f'{R}[异常]{Z} config.yaml 根节点不是映射')
    raise SystemExit(0)
builder = data.get('feishu_messaging_card_builder')
if isinstance(builder, dict):
    print(f'{G}[正常]{Z} 已检测到 feishu_messaging_card_builder 配置')
    for key in ('enabled', 'mode', 'fallback_to_text', 'tool_display_mode'):
        print(f'  - {key}: {builder.get(key)!r}')
    length_protection = builder.get('length_protection')
    if isinstance(length_protection, dict):
        for key in ('max_card_text_length', 'overflow_mode'):
            print(f'  - length_protection.{key}: {length_protection.get(key)!r}')
    raise SystemExit(0)
old = data.get('feishu')
if isinstance(old, dict) and isinstance(old.get('message_card'), dict):
    print(f'{Y}[注意]{Z} 当前仍是旧配置结构 feishu.message_card，尚未迁移到 feishu_messaging_card_builder')
    raise SystemExit(0)
print(f'{Y}[注意]{Z} 未找到 feishu_messaging_card_builder 配置')
PY

分组 "语法校验"
for sh in install.sh check.sh update.sh uninstall.sh; do
  if bash -n "$PACKAGE_DIR/$sh"; then
    正常 "$sh 语法检查通过"
  else
    异常 "$sh 存在语法错误"
  fi
done
if python3 -m py_compile "$PACKAGE_DIR/feishu_card_build"/*.py; then
  正常 "工具包中的 feishu_card_build 构建包编译通过"
else
  异常 "工具包中的 feishu_card_build 构建包编译失败"
fi
if [[ -d "$TARGET_PACKAGE_DIR" ]]; then
  if python3 -m py_compile "$TARGET_PACKAGE_DIR"/*.py; then
    正常 "已安装的 feishu_card_build 构建包编译通过"
  else
    异常 "已安装的 feishu_card_build 构建包编译失败"
  fi
fi

分组 "总结"
if [[ "$STATUS_OK" -eq 1 ]]; then
  echo -e "${COLOR_GREEN}${COLOR_BOLD}整体状态：正常${COLOR_RESET}"
else
  echo -e "${COLOR_YELLOW}${COLOR_BOLD}整体状态：需要关注${COLOR_RESET}"
fi
