#!/usr/bin/env bash
# Small pilot: 4 strategies x 2 workloads at fixed parallelism=8, unpinned.
# Purpose: prove the measurement pipeline works end-to-end and produce a
# feasibility number for the Assignment 1 proposal. NOT the full experiment.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results/pilot

# Grant RAPL access only if a counter is not already readable
# (the grant script needs sudo, so avoid invoking it unnecessarily).
if ! cat /sys/class/powercap/intel-rapl:0/energy_uj >/dev/null 2>&1; then
  ./scripts/enable-rapl.sh
fi

java -jar harness/target/benchmarks.jar \
  -prof nl.utwente.gsd.energy.RaplProfiler \
  -p parallelism=8 \
  -f 2 -wi 5 -i 10 \
  -rf json -rff results/pilot/pilot.json \
  -foe true

echo "Pilot complete: results/pilot/pilot.json"
