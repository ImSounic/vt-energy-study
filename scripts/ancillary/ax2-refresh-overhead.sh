#!/usr/bin/env bash
# AX2 (Mac): overhead of the powermetrics refresher. Idle power over 60 s with
# the refresher at 1000, 250 and 100 ms. Output: results/ancillary/mac/ax2-<ms>.json
source "$(dirname "$0")/common.sh"
[[ $PLATFORM == mac ]] || { echo "AX2 is Mac-only" >&2; exit 1; }
manifest "$OUT/ax2-env.txt"
for ms in 1000 250 100; do
  refresher_start "$ms" "$OUT/ax2-powermetrics-$ms.txt"
  idle 60 "$OUT/ax2-$ms.json"
  refresher_stop; sleep 10
done
echo "AX2 done"
