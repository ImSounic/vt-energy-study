#!/usr/bin/env bash
# Regenerates every analysis output of the A3 report from the committed raw data in results/.
# Usage: ./reproduce.sh [output-dir]   (default: reproduced/; PYTHON overrides the interpreter)
# The measurements themselves need the original hardware; see docs/replication.md.
set -euo pipefail
cd "$(dirname "$0")"
OUT=${1:-reproduced}
PY=${PYTHON:-python3}
mkdir -p "$OUT/mac" "$OUT/intel" "$OUT/ancillary/mac" "$OUT/ancillary/intel" "$OUT/figures"

echo "== Mac main campaign: cell statistics, hypothesis tests, figures (Table 5, Mac columns of Tables 6-8, Figure 1)"
"$PY" analysis/analyse.py --campaign results/mac/main --out "$OUT/mac/analysis" \
  --sleep-d-ms 15.03 --socket-d-ms 12.34

echo "== Mac reused-pool control and Intel reduced campaign: per-cell summaries (reused-pool and MIXED rows, Intel columns of Tables 6-8)"
"$PY" analysis/cell_summary.py results/mac/control --out "$OUT/mac/control-cells.csv"
"$PY" analysis/cell_summary.py results/intel/reduced --out "$OUT/intel/reduced-cells.csv"

echo "== Ancillary experiments (AX3-AX6, SRV)"
for ax in ax3 ax4 ax6; do
  "$PY" analysis/vtenergy/ancillary.py "$ax" "results/ancillary/mac/$ax" > "$OUT/ancillary/mac/$ax-summary.csv"
done
"$PY" analysis/vtenergy/ancillary.py ax5 results/ancillary/mac > "$OUT/ancillary/mac/ax5-summary.csv"
"$PY" analysis/vtenergy/ancillary.py srv results/ancillary/mac > "$OUT/ancillary/mac/srv-summary.csv"
"$PY" analysis/vtenergy/ancillary.py ax5 results/ancillary/intel > "$OUT/ancillary/intel/ax5-summary.csv"

echo "== Report figures (Figures 1 and 2)"
"$PY" analysis/report_figures.py --out "$OUT/figures" --mac-analysis "$OUT/mac/analysis"

echo "done: outputs in $OUT/"
