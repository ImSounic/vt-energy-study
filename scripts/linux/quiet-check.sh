#!/usr/bin/env bash
# Fails unless the machine is quiet enough to measure:
#  1. no denylisted application runs (browsers, Electron apps, chat, media):
#     with 16 CPUs, one busy browser core still leaves 94 % idle, so the idle
#     threshold alone does not enforce the quiet-machine protocol;
#  2. overall CPU idle over a 3 s window is at least MIN_IDLE percent (default 95).
# Linux counterpart of scripts/mac/quiet-check.sh.
# Usage: scripts/linux/quiet-check.sh [min_idle_percent]
set -euo pipefail
min="${1:-95}"
DENY='^(zen-bin|firefox|firefox-bin|Isolated Web Co|chromium|chrome|brave|vivaldi-bin|claude-desktop|claude|electron|Discord|discord|slack|spotify|code|cursor|obs|vlc|mpv|steam|thunderbird|signal-desktop|telegram-desktop)$'
busy=$(ps -eo comm= | grep -E "$DENY" | sort | uniq -c || true)
if [[ -n "$busy" ]]; then
  echo "applications running (quit them first):"; echo "$busy"
  exit 1
fi
idle=$(vmstat 3 2 | tail -1 | awk '{print $15}')
echo "CPU idle over 3 s: ${idle}% (need >= ${min}%)"
ps -eo pcpu,comm --sort=-pcpu | head -6 || true
awk -v i="$idle" -v m="$min" 'BEGIN { exit !(i >= m) }'
