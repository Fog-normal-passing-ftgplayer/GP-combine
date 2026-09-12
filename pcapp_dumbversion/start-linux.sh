#!/usr/bin/env bash
# 懒人包启动器（Linux）：找到本脚本目录后启动助手
set -euo pipefail
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
exec python3 "$HERE/main.py" "$@"
