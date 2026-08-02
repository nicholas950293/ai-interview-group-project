#!/bin/sh
set -u
ulimit -t 10 2>/dev/null || true          # RLIMIT_CPU：CPU 時間上限（研究決策 R-001）
cd /work
printf '%s' "$1" | base64 -d > main.py
printf '%s' "$2" | base64 -d > input.txt
python -m py_compile main.py || exit 90   # 語法錯誤 → COMPILE_ERROR
exec python main.py < input.txt
