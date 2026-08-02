#!/bin/sh
set -u
ulimit -t 10 2>/dev/null || true
cd /work
printf '%s' "$1" | base64 -d > Main.java
printf '%s' "$2" | base64 -d > input.txt
javac -d /work Main.java || exit 90
exec java -XX:MaxRAMPercentage=70 -Djava.io.tmpdir=/work -cp /work Main < input.txt
