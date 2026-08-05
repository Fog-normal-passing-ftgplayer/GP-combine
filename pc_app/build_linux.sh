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
python -m PyInstaller --clean -y gpfusion.spec
echo "输出目录: dist/GP-Fusion配置向导/"
