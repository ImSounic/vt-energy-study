#!/usr/bin/env bash
# Fails unless the machine is quiet enough to measure: overall CPU idle over a
# 3 s window must be at least MIN_IDLE percent (default 95). Linux counterpart
# of scripts/mac/quiet-check.sh.
# Usage: scripts/linux/quiet-check.sh [min_idle_percent]
set -euo pipefail
min="${1:-95}"
idle=$(vmstat 3 2 | tail -1 | awk '{print $15}')
echo "CPU idle over 3 s: ${idle}% (need >= ${min}%)"
ps -eo pcpu,comm --sort=-pcpu | head -6 || true
awk -v i="$idle" -v m="$min" 'BEGIN { exit !(i >= m) }'
