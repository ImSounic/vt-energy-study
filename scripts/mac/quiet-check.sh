#!/usr/bin/env bash
# Fails unless the machine is quiet enough to measure:
#  1. no denylisted application runs (browsers, Electron apps, chat, media):
#     the CPU-idle threshold alone lets one busy browser core through, and the
#     A2 pilot measured 9x idle CPU power with everyday applications open;
#  2. overall CPU idle over a 3 s window is at least MIN_IDLE percent (default 95).
# Usage: scripts/mac/quiet-check.sh [min_idle_percent]
set -euo pipefail
min="${1:-95}"
DENY='^(Safari|Google Chrome|Google Chrome Helper.*|Chromium|Firefox|firefox|zen|Zen|Arc|Brave Browser|Vivaldi|Microsoft Edge|Claude|Claude Helper.*|Discord|Discord Helper.*|Slack|Slack Helper.*|Spotify|Music|TV|Code|Code Helper.*|Cursor|Electron|Microsoft Teams|zoom.us|Mail|Messages|WhatsApp|Telegram|Signal|Notion|Obsidian|Photos|QuickTime Player|VLC|IINA|Steam)$'
busy=$(ps -axo comm= | awk -F/ '{print $NF}' | grep -E "$DENY" | sort | uniq -c || true)
if [[ -n "$busy" ]]; then
  echo "applications running (quit them first):"; echo "$busy"
  exit 1
fi
idle=$(top -l 2 -s 3 -n 0 | awk '/CPU usage/ {v=$7} END {sub("%","",v); sub(",",".",v); print v}')
echo "CPU idle over 3 s: ${idle}% (need >= ${min}%)"
ps -Ao pcpu,comm -r | head -6 || true   # head closes the pipe early: SIGPIPE (141) under pipefail
awk -v i="$idle" -v m="$min" 'BEGIN { exit !(i >= m) }'
