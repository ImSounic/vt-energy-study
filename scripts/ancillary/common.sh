#!/usr/bin/env bash
# Shared setup for the ancillary experiments (AX2-AX6, SRV). Sourced, not run.
# Sets REPO, PLATFORM (intel|mac), JAVA, JAR, OUT (results/ancillary/<platform>)
# and helpers: gate, manifest, server_start/server_stop, refresher_start/stop.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "$(uname)" == Darwin ]]; then
  PLATFORM=mac; SCRIPTS="$REPO/scripts/mac"
  export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home}"
else
  PLATFORM=intel; SCRIPTS="$REPO/scripts/linux"
  export JAVA_HOME="${JAVA_HOME:-$HOME/.local/opt/jdk-25}"
fi
JAVA=("$JAVA_HOME/bin/java" --enable-native-access=ALL-UNNAMED)
JAR="$REPO/harness/target/benchmarks.jar"
OUT="$REPO/results/ancillary/$PLATFORM"
mkdir -p "$OUT"
[[ -f "$JAR" ]] || { echo "missing $JAR: mvn -DskipTests package in harness/" >&2; exit 1; }
if [[ $PLATFORM == intel ]]; then
  cat /sys/class/powercap/intel-rapl:0/energy_uj >/dev/null 2>&1 \
    || { echo "RAPL not readable; run: sudo scripts/enable-rapl.sh" >&2; exit 1; }
fi

# Quiet gate with retries (A3-D10): 30 attempts, 20 s apart.
gate() {
  for _ in $(seq 30); do
    bash "$SCRIPTS/quiet-check.sh" "${MIN_IDLE:-95}" >/dev/null && return 0
    sleep 20
  done
  echo "machine never became quiet" >&2; exit 1
}

manifest() { bash "$SCRIPTS/env-manifest.sh" "$1" >/dev/null; }

SERVER_PID=""
server_start() {  # $1 = port, $2 = stats.json
  local cmd=("${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.workload.SocketDelayServer "$1" 10 "$2")
  if [[ $PLATFORM == intel ]]; then
    source "$REPO/scripts/topology.sh"
    cmd=(taskset -c "${E_CORES##*-}" "${cmd[@]}")  # last E core, as in run_experiment.py
  fi
  "${cmd[@]}" > "$OUT/.server.out" &
  SERVER_PID=$!
  for _ in $(seq 50); do grep -q READY "$OUT/.server.out" 2>/dev/null && return 0; sleep 0.2; done
  echo "SocketDelayServer did not start" >&2; exit 1
}
server_stop() { [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" && wait "$SERVER_PID" 2>/dev/null || true; SERVER_PID=""; }

refresher_start() {  # mac only: $1 = interval ms, $2 = log file
  [[ $PLATFORM == mac ]] || return 0
  bash "$SCRIPTS/powermetrics-start.sh" "$1" "$2" >/dev/null
}
refresher_stop() { [[ $PLATFORM == mac ]] || return 0; bash "$SCRIPTS/powermetrics-stop.sh"; }

idle() { gate; "${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.energy.IdleBaseline "$1" "$2" >/dev/null; }
probe() { "${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.tools.LoadProbe "$@" >/dev/null; }

# Mac: stay awake and keep the sudo ticket alive (powermetrics) for the whole script.
KEEPALIVE=""
if [[ $PLATFORM == mac ]]; then
  caffeinate -i -s -w $$ &
  sudo -v
  while true; do sudo -n true; sleep 60; done 2>/dev/null &
  KEEPALIVE=$!
fi
trap 'server_stop; refresher_stop; [[ -n "$KEEPALIVE" ]] && kill "$KEEPALIVE" 2>/dev/null || true' EXIT
