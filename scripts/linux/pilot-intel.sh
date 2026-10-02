#!/usr/bin/env bash
# Intel feasibility pilot, the counterpart of scripts/mac/pilot-mac.sh:
# same constructs, parallelism and workloads, 3 forks x (warmup + 5 x 5 s),
# RAPL read at iteration boundaries, idle baselines before and after.
# Per the A2 plan (D9b) CPU-bound runs heat-soak for 60 s of warmup so the
# measured window lies in the sustained power regime; IO runs warm up 5 x 1 s.
# Prerequisites: sudo scripts/enable-rapl.sh (once per boot); quiet machine.
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT="results/pilot-intel"
export JAVA_HOME="${JAVA_HOME:-$HOME/.local/opt/jdk-25}"
JAVA=("$JAVA_HOME/bin/java" --enable-native-access=ALL-UNNAMED)
JAR="harness/target/benchmarks.jar"
mkdir -p "$OUT"

cat /sys/class/powercap/intel-rapl:0/energy_uj >/dev/null 2>&1 \
  || { echo "RAPL not readable; run: sudo scripts/enable-rapl.sh" >&2; exit 1; }
scripts/linux/quiet-check.sh "${MIN_IDLE:-95}" || { echo "machine not quiet; close apps and retry" >&2; exit 1; }
scripts/linux/env-manifest.sh "$OUT/env.txt"

"${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.energy.IdleBaseline 60 "$OUT/idle-start.json"

# CPU-bound: 12 x 5 s warmup = 60 s heat-soak (D9b), then 5 x 5 s measured.
"${JAVA[@]}" -jar "$JAR" \
  -prof nl.utwente.gsd.energy.RaplProfiler \
  -p strategy=PLATFORM_THREADS,FIXED_POOL,FORK_JOIN,VIRTUAL_THREADS \
  -p parallelism=8 -p workloadType=CPU \
  -f 3 -wi 12 -w 5s -i 5 -r 5s \
  -rf json -rff "$OUT/pilot-cpu.json" -foe true

# IO (sleep): same settings as the Mac pilot.
"${JAVA[@]}" -jar "$JAR" \
  -prof nl.utwente.gsd.energy.RaplProfiler \
  -p strategy=PLATFORM_THREADS,FIXED_POOL,FORK_JOIN,VIRTUAL_THREADS \
  -p parallelism=8 -p workloadType=IO \
  -f 3 -wi 5 -w 1s -i 5 -r 5s \
  -rf json -rff "$OUT/pilot-io.json" -foe true

"${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.energy.IdleBaseline 60 "$OUT/idle-end.json"

python3 - "$OUT" <<'PY'
import json, sys
out = sys.argv[1]
rows = json.load(open(f"{out}/pilot-cpu.json")) + json.load(open(f"{out}/pilot-io.json"))
json.dump(rows, open(f"{out}/pilot.json", "w"), indent=1)
print(f"merged {len(rows)} benchmark rows into {out}/pilot.json")
PY
scripts/linux/env-manifest.sh "$OUT/env-end.txt"
echo "Intel pilot complete: $OUT"
