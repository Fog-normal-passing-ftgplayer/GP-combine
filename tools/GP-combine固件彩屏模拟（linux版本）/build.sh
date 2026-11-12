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

# 1) 检查 .ino.cpp 是否就绪
#    arduino-cli 那一步（几分钟）已经拆到 compile_ino.sh，这里只做检查：
#    缺文件或比固件源码旧就明确报错，不擅自跑工具链。
#    这样改仿真器本身时几秒就能编完；改固件时也知道慢的是哪一步。
_auto_needed() {
  [ ! -f "$SRC" ] && return 0
  local st="$BUILD/.ino_src_hash"
  [ -f "$st" ] || return 0
  [ "$(cat "$st")" != "$( cd "$SKETCH" && cat *.ino *.h 2>/dev/null | sha256sum | cut -d' ' -f1 )" ]
}
if [ "${AUTO_INO:-0}" = "1" ] && _auto_needed; then
  echo "[build] AUTO_INO=1：自动调用 compile_ino.sh"
  "$SIM/compile_ino.sh" "$([ "$NAME" = "esp32_170x320" ] && echo 320 || echo 240)"
fi

if [ ! -f "$SRC" ]; then
  echo "缺少 $SRC" >&2
  echo "先单独生成一次（arduino-cli，几分钟）：" >&2
  echo "  ./compile_ino.sh $([ "$NAME" = "esp32_170x320" ] && echo 320 || echo 240)" >&2
  exit 1
fi

# 用源码内容哈希判断过期（mtime 不可靠：arduino-cli 增量缓存不重写未变产物）
STAMP="$BUILD/.ino_src_hash"
NOW_HASH="$( cd "$SKETCH" && cat *.ino *.h 2>/dev/null | sha256sum | cut -d' ' -f1 )"
if [ -f "$STAMP" ] && [ "$(cat "$STAMP")" != "$NOW_HASH" ]; then
  echo "[build] ✘ 固件源码变了，.ino.cpp 已过期（仿真器会用到旧代码）" >&2
  echo "        先跑：./compile_ino.sh $([ "$NAME" = "esp32_170x320" ] && echo 320 || echo 240)" >&2
  echo "        （或在这次构建加 AUTO_INO=1 自动重新生成）" >&2
  exit 1
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

# 4) 构建形态
#    HEADLESS=1 -> 不编图形后端，输出短名 build/sim240 | build/sim320（配置助手直接调用）
#    默认       -> 带 X11 窗口，输出 build/sim_<sketch>
if [ "${LIB:-0}" = "1" ]; then
  OUT="$SIM/build/libsim$([ "$SIM_W" = "320" ] && echo 320 || echo 240).so"
  FLAGS=(-O2 -fPIC -shared -DSIM_LIB)
  LIBS=(-lz)
  echo "[build] 共享库构建（配置助手内嵌预览）"
elif [ "${HEADLESS:-0}" = "1" ]; then
  OUT="$SIM/build/sim$([ "$SIM_W" = "320" ] && echo 320 || echo 240)"
  FLAGS=(-O2 -DSIM_HEADLESS)
  LIBS=(-lz)
  echo "[build] headless 构建（无窗口）"
else
  OUT="$SIM/build/sim_$NAME"
  FLAGS=(-O0)
  LIBS=(-lz -lX11)
fi

echo "[build] $NAME  ${SIM_W}x${SIM_H}"
g++ -std=gnu++17 "${FLAGS[@]}" -w -fno-exceptions \
    -DSIM_IMG_W="$SIM_W" -DSIM_IMG_H="$SIM_H" \
    -I "$SIM/shim" -I "$SKETCH" -I "$GEN" \
    "$SIM/sim_main.cpp" "${EXTRA[@]}" \
    -o "$OUT" "${LIBS[@]}"

echo "[build] OK -> $OUT"
echo "[build] 试跑：./run.sh $NAME --mode=keys --scale=3"
