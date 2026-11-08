#!/bin/sh
# 编译并跑主机侧回归测试（不需要开发板）
set -e
cd "$(dirname "$0")/../.."
CXX=${CXX:-g++}
OUT=$(mktemp -d)/fixes_test
"$CXX" -std=c++17 -Wall -Wextra -o "$OUT" tools/host_tests/fixes_test.cpp
"$OUT"
