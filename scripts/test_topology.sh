#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/topology.sh"

fail=0
check() {
  if [[ "$2" == "$3" ]]; then echo "PASS: $1"; else echo "FAIL: $1 (got '$2', want '$3')"; fail=1; fi
}

check "P-cores"   "$P_CORES"   "0-5"
check "E-cores"   "$E_CORES"   "6-13"
check "LP-E cores" "$LPE_CORES" "14-15"
check "all cores" "$ALL_CORES" "0-15"
exit $fail
