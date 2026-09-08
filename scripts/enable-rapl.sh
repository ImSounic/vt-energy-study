#!/usr/bin/env bash
# Grants the invoking user read access to RAPL energy counters.
# Must be re-run after every reboot (sysfs is recreated).
set -euo pipefail
command -v setfacl >/dev/null || { echo "error: setfacl not installed" >&2; exit 1; }
USER_NAME="${SUDO_USER:-$USER}"
if [[ "$USER_NAME" == "root" ]]; then echo "warn: USER_NAME resolved to root; grant is a no-op for root" >&2; fi
count=0
for f in /sys/class/powercap/intel-rapl:*/energy_uj; do
  [[ -e "$f" ]] || continue
  if sudo setfacl -m "u:${USER_NAME}:r" "$f"; then count=$((count+1)); else echo "warn: failed on $f" >&2; fi
done
echo "Granted read access on $count RAPL domain(s) to ${USER_NAME}"
