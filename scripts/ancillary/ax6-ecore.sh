#!/usr/bin/env bash
# AX6 (Mac): E-core confinement of BACKGROUND QoS and its frequency effect:
# 6 busy threads for 20 s under DEFAULT and under taskpolicy -b, with
# powermetrics logging cluster residency. Output: results/ancillary/mac/ax6/
source "$(dirname "$0")/common.sh"
[[ $PLATFORM == mac ]] || { echo "AX6 is Mac-only" >&2; exit 1; }
mkdir -p "$OUT/ax6"; manifest "$OUT/ax6/env.txt"
refresher_start 100 "$OUT/ax6/powermetrics.txt"
gate; echo "AX6 default";    probe 6 20 "$OUT/ax6/default.json"; sleep 10
gate; echo "AX6 background"; taskpolicy -b "${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.tools.LoadProbe 6 20 "$OUT/ax6/background.json" >/dev/null
echo "AX6 done (analyse with: .venv/bin/python analysis/vtenergy/ancillary.py ax6 $OUT/ax6)"
