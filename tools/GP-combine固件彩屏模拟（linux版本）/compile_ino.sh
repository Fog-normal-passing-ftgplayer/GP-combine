#!/usr/bin/env bash
# 单独生成 .ino.cpp（arduino-cli 预处理产物，带自动函数原型）。
#
# 为什么要单独一步：arduino-cli 要跑 ESP32 工具链，几分钟；而编仿真器/共享库
# 只要几秒。拆开之后改仿真器本身不用等工具链，改固件时也明确知道慢在哪一步。
#
#   ./compile_ino.sh          # 两个分辨率都编
#   ./compile_ino.sh 240      # 只编 240x135
#   ./compile_ino.sh 320      # 只编 170x320
set -euo pipefail

SIM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SIM/../.." && pwd)"
FQBN="${FQBN:-esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=custom}"

command -v arduino-cli >/dev/null 2>&1 || {
  echo "找不到 arduino-cli。装好后还要装 esp32 支持包：" >&2
  echo "  arduino-cli core install esp32:esp32" >&2
  exit 1
}

compile_one() {
  local dir="$1"
  local sketch="$REPO/$dir"
  local name
  name="$(basename "$sketch")"
  local build="$SIM/build/$name"
  echo "[ino] $name：调用 arduino-cli（较慢，几分钟）…"
  arduino-cli compile --fqbn "$FQBN" --build-path "$build" "$sketch"
  local src="$build/sketch/$name.ino.cpp"
  [ -f "$src" ] || { echo "[ino] ✘ 没生成 $src" >&2; return 1; }
  # 记下源码内容哈希：build.sh 靠它判断 .ino.cpp 是否过期。
  # 不用 mtime —— arduino-cli 增量缓存不会重写未变的产物，mtime 会误判。
  ( cd "$sketch" && cat *.ino *.h 2>/dev/null | sha256sum | cut -d" " -f1 ) > "$build/.ino_src_hash"
  echo "[ino] ✔ $src  ($(du -k "$src" | cut -f1) KB)"
}

case "${1:-all}" in
  240) compile_one esp32 ;;
  320) compile_one esp32_170x320 ;;
  all) compile_one esp32; compile_one esp32_170x320 ;;
  -h|--help) sed -n '2,12p' "$0" ;;
  *) echo "用法: ./compile_ino.sh [240|320|all]" >&2; exit 1 ;;
esac
echo "[ino] 完成。接下来可以直接 ./build.sh / LIB=1 ./build.sh，或 pc_app/prepare_sim.sh"
