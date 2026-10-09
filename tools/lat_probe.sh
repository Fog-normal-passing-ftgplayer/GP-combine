#!/bin/bash
# 无线延迟实测（本体有线 vs 接收器无线，同键边沿差值）
# 用法: sudo bash tools/lat_probe.sh [秒数]        默认 30 秒
#       sudo bash tools/lat_probe.sh list          只列设备
set -u
here="$(cd "$(dirname "$0")" && pwd)"
arg="${1:-30}"
log=/tmp/lat.txt
touch "$log" 2>/dev/null || true
if [ "$arg" = "list" ]; then
    python3 -u "$here/wireless_latency_probe.py" --list --log "$log"
    exit 0
fi
echo "开始采样 ${arg}s —— 现在开始只按 A 键，每秒一下左右。"
python3 -u "$here/wireless_latency_probe.py" --seconds "$arg" --log "$log"
echo "=== 采样结束，结果也在 $log ==="
