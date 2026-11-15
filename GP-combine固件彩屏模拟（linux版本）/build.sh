#!/usr/bin/env bash
# 把 ESP32 固件的渲染层编到宿主机上跑（宿主机 UI 仿真器）。
#
#   ./build.sh             # 240x135，对应 esp32/
#   ./build.sh 320         # 170x320，对应 esp32_170x320/
#   SKETCH=/path/to/sketch ./build.sh
#
# 首次会自动调 arduino-cli 编译固件，拿到带自动函数原型的 .ino.cpp
# （这是关键：.ino 源码里函数可以先用后定义，宿主机 g++ 必须先有原型）。
set -euo pipefail

SIM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SIM/../.." && pwd)"
FQBN="${FQBN:-esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=custom}"

case "${1:-240}" in
  240)     DEF_SKETCH="$REPO/esp32" ;;
  320)     DEF_SKETCH="$REPO/esp32_170x320" ;;
  -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
  *)       DEF_SKETCH="$1" ;;
esac
SKETCH="${SKETCH:-$DEF_SKETCH}"
NAME="$(basename "$SKETCH")"
BUILD="${BUILD:-$SIM/build/$NAME}"
GEN="$SIM/build/gen"
SRC="$BUILD/sketch/$NAME.ino.cpp"

[ -d "$SKETCH" ] || { echo "找不到 sketch 目录: $SKETCH" >&2; exit 1; }

# 1) 生成带原型的 .ino.cpp
if [ ! -f "$SRC" ]; then
  if command -v arduino-cli >/dev/null 2>&1; then
    echo "[build] 首次：调用 arduino-cli 生成 .ino.cpp（几分钟，只做一次）"
    arduino-cli compile --fqbn "$FQBN" --build-path "$BUILD" "$SKETCH"
  else
    echo "缺少 $SRC" >&2
    echo "需要先用 arduino-cli 编一次固件，例如：" >&2
    echo "  arduino-cli compile --fqbn '$FQBN' --build-path '$BUILD' '$SKETCH'" >&2
    exit 1
  fi
fi

mkdir -p "$GEN"
cp "$SRC" "$GEN/esp32.ino.cpp"

# 2) 屏幕尺寸直接读固件的 SCR_W/SCR_H，读不到退回 240x135
GW=$(sed -n 's/^#define[[:space:]]*SCR_W[[:space:]]*\([0-9]\{1,\}\).*/\1/p' "$SRC" | head -1)
GH=$(sed -n 's/^#define[[:space:]]*SCR_H[[:space:]]*\([0-9]\{1,\}\).*/\1/p' "$SRC" | head -1)
SIM_W="${SIM_W:-${GW:-240}}"
SIM_H="${SIM_H:-${GH:-135}}"

# 3) 附带源码：170x320 版内嵌 NES 模拟器，src/ 下的 .cpp 必须一起编
EXTRA=()
if [ -d "$SKETCH/src" ]; then
  while IFS= read -r f; do EXTRA+=("$f"); done < <(find "$SKETCH/src" -name '*.cpp')
  echo "[build] 附带源码 ${#EXTRA[@]} 个（内嵌 NES）"
fi

echo "[build] $NAME  ${SIM_W}x${SIM_H}"
g++ -std=gnu++17 -O0 -w -fno-exceptions \
    -DSIM_IMG_W="$SIM_W" -DSIM_IMG_H="$SIM_H" \
    -I "$SIM/shim" -I "$SKETCH" -I "$GEN" \
    "$SIM/sim_main.cpp" "${EXTRA[@]}" \
    -o "$SIM/build/sim_$NAME" -lz -lX11

echo "[build] OK -> tools/ui_sim/build/sim_$NAME"
echo "[build] 试跑：./run.sh $NAME --mode=keys --scale=3"
