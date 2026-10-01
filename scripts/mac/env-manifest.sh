#!/usr/bin/env bash
# Records the hardware/software environment of a measurement batch.
# Usage: scripts/mac/env-manifest.sh <out-file>
set -euo pipefail
out="$1"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home}"
{
  echo "# date (UTC)";   date -u +%Y-%m-%dT%H:%M:%SZ
  echo "# git";          git -C "$repo" rev-parse HEAD; git -C "$repo" status --short | head -20 || true
  echo "# os";           sw_vers; uname -a
  echo "# hardware";     sysctl hw.model machdep.cpu.brand_string hw.memsize hw.ncpu \
                           hw.perflevel0.physicalcpu hw.perflevel1.physicalcpu
  echo "# power";        pmset -g; pmset -g batt | head -1 || true; pmset -g therm
  echo "# java";         "$JAVA_HOME/bin/java" -version 2>&1
  echo "# uptime/load";  uptime
  echo "# top processes by cpu"; ps -Ao pcpu,comm -r | head -11 || true
} > "$out" 2>&1
echo "wrote $out"
