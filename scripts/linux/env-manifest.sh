#!/usr/bin/env bash
# Records the hardware/software environment of a measurement batch on Linux.
# Usage: scripts/linux/env-manifest.sh <out-file>
set -euo pipefail
out="$1"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
JAVA_HOME="${JAVA_HOME:-$HOME/.local/opt/jdk-25}"
{
  echo "# date (UTC)";   date -u +%Y-%m-%dT%H:%M:%SZ
  echo "# git";          git -C "$repo" rev-parse HEAD; git -C "$repo" status --short | head -20 || true
  echo "# os";           grep -E '^(NAME|VERSION_ID|PRETTY_NAME)=' /etc/os-release; uname -a
  echo "# cpu";          lscpu | grep -E 'Model name|^CPU\(s\)|Thread|MHz'
  echo "# core classes"; source "$repo/scripts/topology.sh"; echo "P=$P_CORES E=$E_CORES LPE=$LPE_CORES"
  echo "# memory";       free -h | head -2
  echo "# frequency control"
  echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
  echo "intel_pstate status: $(cat /sys/devices/system/cpu/intel_pstate/status)"
  echo "no_turbo: $(cat /sys/devices/system/cpu/intel_pstate/no_turbo)"
  echo "hwp_dynamic_boost: $(cat /sys/devices/system/cpu/intel_pstate/hwp_dynamic_boost 2>/dev/null || echo n/a)"
  echo "# power";        echo "AC online: $(cat /sys/class/power_supply/AC*/online 2>/dev/null | head -1)"
  for d in /sys/class/powercap/intel-rapl:*; do
    [[ -e "$d/name" ]] || continue
    printf "rapl %s (%s):" "$(basename "$d")" "$(cat "$d/name")"
    for c in 0 1; do
      [[ -e "$d/constraint_${c}_name" ]] || continue
      printf " %s=%s uW/%s us" "$(cat "$d/constraint_${c}_name")" "$(cat "$d/constraint_${c}_power_limit_uw")" "$(cat "$d/constraint_${c}_time_window_us")"
    done; echo
  done
  echo "# thermal";      for h in /sys/class/hwmon/hwmon*; do [[ "$(cat "$h/name")" == coretemp ]] && cat "$h"/temp*_input | awk '{s+=$1; if($1>m)m=$1} END{printf "coretemp max %.1f C\n", m/1000}'; done
  echo "# java";         "$JAVA_HOME/bin/java" -version 2>&1
  echo "# uptime/load";  uptime
  echo "# top processes by cpu"; ps -eo pcpu,comm --sort=-pcpu | head -11 || true
} > "$out" 2>&1
echo "wrote $out"
