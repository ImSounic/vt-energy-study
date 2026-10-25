#!/usr/bin/env bash
# AX3 (Mac): read path. IOReport CPU_Energy power from LoadProbe against the
# CPU Power that powermetrics (same energy model) logs over the same window,
# at 1, 4 and 10 busy threads. Output: results/ancillary/mac/ax3/
source "$(dirname "$0")/common.sh"
[[ $PLATFORM == mac ]] || { echo "AX3 is Mac-only" >&2; exit 1; }
mkdir -p "$OUT/ax3"; manifest "$OUT/ax3/env.txt"
refresher_start 100 "$OUT/ax3/powermetrics.txt"
for k in 1 4 10; do gate; echo "AX3 k=$k"; probe "$k" 20 "$OUT/ax3/k$k.json"; sleep 10; done
echo "AX3 done (analyse with: .venv/bin/python analysis/vtenergy/ancillary.py ax3 $OUT/ax3)"
