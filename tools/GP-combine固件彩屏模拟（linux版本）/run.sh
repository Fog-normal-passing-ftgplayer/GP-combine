#!/usr/bin/env bash
# 运行仿真器（先 ./build.sh）
#   ./run.sh                 # 240x135，默认图形窗口
#   ./run.sh 320             # 170x320
#   ./run.sh 320 --mode=tour --script=tours/320.tour --out=shots/320 --step=8
set -euo pipefail
SIM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-240}" in
  240) NAME=esp32 ;;
  320) NAME=esp32_170x320 ;;
  *)   NAME="$1" ;;
esac
shift || true
BIN="$SIM/build/sim_$NAME"
[ -x "$BIN" ] || { echo "还没编译：先跑 ./build.sh ${NAME/esp32_170x320/320}" >&2; exit 1; }
exec "$BIN" "$@"
