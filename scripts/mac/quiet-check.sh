#!/usr/bin/env bash
# Fails unless the machine is quiet enough to measure: overall CPU idle over a
# 3 s window must be at least MIN_IDLE percent (default 95).
# Usage: scripts/mac/quiet-check.sh [min_idle_percent]
set -euo pipefail
min="${1:-95}"
idle=$(top -l 2 -s 3 -n 0 | awk '/CPU usage/ {v=$7} END {sub("%","",v); sub(",",".",v); print v}')
echo "CPU idle over 3 s: ${idle}% (need >= ${min}%)"
ps -Ao pcpu,comm -r | head -6 || true   # head closes the pipe early: SIGPIPE (141) under pipefail
awk -v i="$idle" -v m="$min" 'BEGIN { exit !(i >= m) }'
