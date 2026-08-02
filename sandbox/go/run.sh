#!/bin/sh
set -u
ulimit -t 10 2>/dev/null || true
cd /work
printf '%s' "$1" | base64 -d > main.go
printf '%s' "$2" | base64 -d > input.txt
go build -o app main.go || exit 90
exec ./app < input.txt
