#!/bin/bash
# Cursor Agent hook（create-hook 推荐形态：~/.cursor/hooks/ 下的可执行脚本）
# 由 install.py 写入绝对路径；stdin JSON → scan.py --hook cursor → stdout JSON
set -euo pipefail
exec "__AUDITION_PYTHON__" "__AUDITION_ROOT__/scan.py" --hook cursor
