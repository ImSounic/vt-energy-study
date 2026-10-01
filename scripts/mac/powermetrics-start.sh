#!/usr/bin/env bash
# Starts powermetrics as root in the background. On macOS 27 it is what
# refreshes the IOReport energy counters (frozen otherwise); it also logs
# cluster residency/frequency and thermal pressure.
# Usage: scripts/mac/powermetrics-start.sh <interval_ms> <log-file>
set -euo pipefail
interval="$1"; log="$2"
sudo -v
sudo powermetrics --samplers cpu_power,thermal -i "$interval" -o "$log" >/dev/null 2>&1 &
sleep 2
pgrep -x powermetrics >/dev/null || { echo "error: powermetrics did not start" >&2; exit 1; }
echo "powermetrics running at ${interval} ms -> $log"
