#!/usr/bin/env bash
# 构建 Linux 版 GP-Fusion 配置向导
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

# 真机预览用的 headless 仿真器：构建并放进 gpfusion_wizard/bin/
# （找不到源码目录不会失败，只是预览退化为静态图）
./prepare_sim.sh

python -m PyInstaller --clean -y gpfusion.spec
echo "输出目录: dist/GPFusionWizard/"
