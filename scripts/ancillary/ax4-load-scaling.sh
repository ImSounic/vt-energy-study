#!/usr/bin/env bash
# AX4: linearity of the energy counters under load. k = 0..N busy threads
# (N = 16 on Intel, 10 on the Mac), 20 s each, 10 s cooldown, in a seeded
# random order. Output: results/ancillary/<platform>/ax4/k<k>.json
source "$(dirname "$0")/common.sh"
N=$([[ $PLATFORM == intel ]] && echo 16 || echo 10)
mkdir -p "$OUT/ax4"
manifest "$OUT/ax4/env.txt"
refresher_start 100 "$OUT/ax4/powermetrics.txt"
for k in $(seq 0 "$N" | python3 -c 'import random,sys; v=sys.stdin.read().split(); random.Random(4).shuffle(v); print(*v)'); do
  gate; echo "AX4 k=$k"; probe "$k" 20 "$OUT/ax4/k$k.json"; sleep 10
done
echo "AX4 done: $OUT/ax4 (analyse with: .venv/bin/python analysis/vtenergy/ancillary.py ax4 $OUT/ax4)"
