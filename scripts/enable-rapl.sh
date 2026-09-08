#!/usr/bin/env bash
# Grants the invoking user read access to RAPL energy counters.
# Must be re-run after every reboot (sysfs is recreated).
set -euo pipefail
USER_NAME="${SUDO_USER:-$USER}"
count=0
for f in /sys/class/powercap/intel-rapl:*/energy_uj; do
  [[ -e "$f" ]] || continue
  sudo setfacl -m "u:${USER_NAME}:r" "$f" && count=$((count+1))
done
echo "Granted read access on $count RAPL domain(s) to ${USER_NAME}"
