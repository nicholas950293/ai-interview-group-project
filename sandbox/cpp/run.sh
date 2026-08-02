#!/bin/sh
set -u
ulimit -t 10 2>/dev/null || true
cd /work
printf '%s' "$1" | base64 -d > main.cpp
printf '%s' "$2" | base64 -d > input.txt
g++ -O2 -std=c++20 -o app main.cpp || exit 90
exec ./app < input.txt
