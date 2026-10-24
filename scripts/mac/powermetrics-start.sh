#!/usr/bin/env bash
# Starts powermetrics as root in the background. On macOS 27 it is what
# refreshes the IOReport energy counters (frozen otherwise); it also logs
# cluster residency/frequency and thermal pressure.
# Usage: scripts/mac/powermetrics-start.sh <interval_ms> <log-file>
# Asks for the sudo password only when run from a terminal; unattended
# (stdin not a tty, as run_experiment.py calls it) an expired ticket fails at
# once instead of hanging at a password prompt.
set -euo pipefail
interval="$1"; log="$2"
if ! sudo -n true 2>/dev/null; then
  [[ -t 0 ]] || { echo "error: sudo ticket expired (run sudo -v)" >&2; exit 1; }
  sudo -v
fi
sudo -n powermetrics --samplers cpu_power,thermal -i "$interval" -o "$log" >/dev/null 2>&1 &
sleep 2
pgrep -x powermetrics >/dev/null || { echo "error: powermetrics did not start" >&2; exit 1; }
echo "powermetrics running at ${interval} ms -> $log"
