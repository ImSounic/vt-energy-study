#!/usr/bin/env bash
# Grants the invoking user read access to RAPL energy counters.
# Must be re-run after every reboot (sysfs is recreated).
#
# Primary mechanism: a POSIX ACL scoped to the invoking user. Some kernels
# (observed: CachyOS 7.2) reject ACLs on sysfs with "Operation not supported";
# for those we fall back to chmod a+r, which is world-readable rather than
# user-scoped. Energy counters are not secret on a single-user research
# machine, but the widened scope is reported so it can be stated in the paper.
set -euo pipefail
USER_NAME="${SUDO_USER:-$USER}"
if [[ "$USER_NAME" == "root" ]]; then echo "warn: USER_NAME resolved to root; grant is a no-op for root" >&2; fi
have_setfacl=0
command -v setfacl >/dev/null && have_setfacl=1
acl_count=0
chmod_count=0
fail_count=0
for f in /sys/class/powercap/intel-rapl:*/energy_uj; do
  [[ -e "$f" ]] || continue
  if [[ $have_setfacl -eq 1 ]] && sudo setfacl -m "u:${USER_NAME}:r" "$f" 2>/dev/null; then
    acl_count=$((acl_count+1))
  elif sudo chmod a+r "$f"; then
    chmod_count=$((chmod_count+1))
  else
    echo "warn: failed on $f" >&2
    fail_count=$((fail_count+1))
  fi
done
echo "Granted read access: ${acl_count} via ACL, ${chmod_count} via chmod a+r, ${fail_count} failed (user: ${USER_NAME})"
if [[ $((acl_count + chmod_count)) -eq 0 ]]; then
  echo "error: no RAPL domain is readable; measurements cannot run" >&2
  exit 1
fi
