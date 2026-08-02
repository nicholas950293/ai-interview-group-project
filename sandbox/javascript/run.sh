#!/bin/sh
set -u
ulimit -t 10 2>/dev/null || true
cd /work
printf '%s' "$1" | base64 -d > main.js
printf '%s' "$2" | base64 -d > input.txt
node --check main.js || exit 90
exec node main.js < input.txt
