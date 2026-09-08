#!/usr/bin/env bash
# Detects hybrid core classes by scheduler capacity.
# Exports P_CORES, E_CORES, LPE_CORES, ALL_CORES as taskset-compatible ranges.

_collapse() {
  # Turn "0 1 2 3 5" into "0-3,5"
  local nums=($1) out="" start prev
  [[ ${#nums[@]} -eq 0 ]] && { echo ""; return; }
  start=${nums[0]}; prev=${nums[0]}
  for n in "${nums[@]:1}"; do
    if (( n == prev + 1 )); then prev=$n; continue; fi
    if (( start == prev )); then out+="${start},"; else out+="${start}-${prev},"; fi
    start=$n; prev=$n
  done
  if (( start == prev )); then out+="${start}"; else out+="${start}-${prev}"; fi
  echo "$out"
}

declare -A _by_cap
for c in /sys/devices/system/cpu/cpu[0-9]*; do
  n=$(basename "$c" | tr -d 'cpu')
  cap=$(cat "$c/cpu_capacity" 2>/dev/null || echo 0)
  _by_cap[$cap]+="$n "
done

# Sort distinct capacities descending: highest = P, lowest = LP-E
_caps=($(printf '%s\n' "${!_by_cap[@]}" | sort -rn))

_sorted() { printf '%s\n' $1 | sort -n | tr '\n' ' '; }

P_CORES=$(_collapse "$(_sorted "${_by_cap[${_caps[0]}]}")")
if [[ ${#_caps[@]} -ge 3 ]]; then
  E_CORES=$(_collapse "$(_sorted "${_by_cap[${_caps[1]}]}")")
  LPE_CORES=$(_collapse "$(_sorted "${_by_cap[${_caps[2]}]}")")
elif [[ ${#_caps[@]} -eq 2 ]]; then
  E_CORES=$(_collapse "$(_sorted "${_by_cap[${_caps[1]}]}")")
  LPE_CORES=""
else
  E_CORES=""; LPE_CORES=""
fi
ALL_CORES="0-$(($(nproc) - 1))"

export P_CORES E_CORES LPE_CORES ALL_CORES
