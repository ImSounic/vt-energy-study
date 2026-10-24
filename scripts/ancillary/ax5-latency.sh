#!/usr/bin/env bash
# AX5: calibration of the per-task wait d: 10^4 Thread.sleep(10) calls per
# thread kind and 10^3 SOCKET round trips; on the Mac repeated under
# BACKGROUND QoS (taskpolicy -b). Output: results/ancillary/<platform>/ax5-*.json
source "$(dirname "$0")/common.sh"
manifest "$OUT/ax5-env.txt"
server_start 31002 "$OUT/ax5-server.json"
gate; echo "AX5 default"
"${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.tools.LatencyCalibration "$OUT/ax5-default.json" 10000 31002 1000 >/dev/null
if [[ $PLATFORM == mac ]]; then
  gate; echo "AX5 background"
  taskpolicy -b "${JAVA[@]}" -cp "$JAR" nl.utwente.gsd.tools.LatencyCalibration "$OUT/ax5-background.json" 10000 31002 1000 >/dev/null
fi
echo "AX5 done"; cat "$OUT"/ax5-*.json
