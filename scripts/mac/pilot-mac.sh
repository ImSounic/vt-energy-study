#!/usr/bin/env bash
# Mac feasibility pilot for Assignment 2 (~20 min). Follow the quiet-machine
# protocol in the A2 plan first (quit all apps, Wi-Fi off, Spotlight paused).
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT="results/pilot-mac"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home}"
JAVA=("$JAVA_HOME/bin/java" --enable-native-access=ALL-UNNAMED)
JAR="harness/target/benchmarks.jar"
mkdir -p "$OUT"

scripts/mac/quiet-check.sh 95 || { echo "machine not quiet; quit apps and retry" >&2; exit 1; }
scripts/mac/env-manifest.sh "$OUT/env.txt"
caffeinate -i -s -w $$ &
sudo -v
while true; do sudo -n true; sleep 60; done 2>/dev/null &   # keep sudo alive for the final stop
KEEPALIVE=$!
trap 'scripts/mac/powermetrics-stop.sh; kill $KEEPALIVE 2>/dev/null' EXIT

# Idle power with the refresher at 1000 ms (reference for powermetrics' own overhead)
scripts/mac/powermetrics-start.sh 1000 "$OUT/powermetrics-1000ms.txt"
"${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.energy.IdleBaseline 60 "$OUT/idle-1000ms.json"
scripts/mac/powermetrics-stop.sh

# Experiment refresh rate: 100 ms
scripts/mac/powermetrics-start.sh 100 "$OUT/powermetrics-100ms.txt"
"${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.energy.IdleBaseline 60 "$OUT/idle-start.json"
"${JAVA[@]}" -jar "$JAR" \
  -prof nl.utwente.gsd.energy.IoReportProfiler \
  -p strategy=PLATFORM_THREADS,FIXED_POOL,FORK_JOIN,VIRTUAL_THREADS \
  -p parallelism=8 -p workloadType=CPU,IO \
  -f 3 -wi 5 -w 1s -i 5 -r 5s \
  -rf json -rff "$OUT/pilot.json" -foe true
"${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.energy.IdleBaseline 60 "$OUT/idle-end.json"
echo "Mac pilot complete: $OUT"
