#!/usr/bin/env bash
# 构建 headless 仿真器并把二进制放进助手包（供「GIF 页真机预览」调用）。
#
#   ./prepare_sim.sh            构建 240 + 320 并复制到 gpfusion_wizard/bin/
#   ./prepare_sim.sh --check    只检查现有二进制，不重新构建
#
# 找不到仿真器源码目录时给出提示但不失败 —— 预览会降级成静态图，不影响向导其它功能。
set -euo pipefail
cd "$(dirname "$0")"

DEST="gpfusion_wizard/bin"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

# 源码目录名可能被改过（含中文），靠 sim_main.cpp 定位
SIM_DIR=""
if compgen -G "../tools/*/sim_main.cpp" > /dev/null 2>&1; then
  SIM_DIR="$(cd "$(dirname "$(ls ../tools/*/sim_main.cpp | head -1)")" && pwd)"
fi

if [ -z "$SIM_DIR" ]; then
  echo "[sim] 未找到仿真器源码（tools/*/sim_main.cpp）"
  echo "[sim] 跳过 —— 向导仍可正常生成固件，只是右侧预览退化为静态图"
  exit 0
fi
echo "[sim] 仿真器目录: $SIM_DIR"

need_build=0
for v in 240 320; do
  [ -f "$SIM_DIR/build/libsim$v.so" ] || need_build=1
done
if [ "$need_build" = "1" ] && [ "$CHECK_ONLY" = "0" ]; then
  for v in 240 320; do
    echo "[sim] 构建共享库 $v…"
    ( cd "$SIM_DIR" && LIB=1 ./build.sh "$v" >/dev/null )
  done
fi

mkdir -p "$DEST"
for v in 240 320; do
  src="$SIM_DIR/build/libsim$v.so"
  if [ -f "$src" ]; then
    cp -f "$src" "$DEST/libsim$v.so"
    echo "[sim] ✔ $DEST/libsim$v.so  ($(du -k "$DEST/libsim$v.so" | cut -f1) KB)"
  else
    echo "[sim] ✘ 缺少 $src —— 该分辨率下真机预览不可用"
  fi
done
