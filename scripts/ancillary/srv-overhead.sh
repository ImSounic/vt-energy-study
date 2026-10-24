#!/usr/bin/env bash
# SRV: idle overhead of the SOCKET server, as an A-B-A sequence of 60 s idle
# baselines (without, with, without the server). Its per-request CPU time is in
# each campaign batch's server.json. Output: results/ancillary/<platform>/srv-*.json
source "$(dirname "$0")/common.sh"
manifest "$OUT/srv-env.txt"
refresher_start 100 "$OUT/srv-powermetrics.txt"
idle 60 "$OUT/srv-without-1.json"
server_start 31003 "$OUT/srv-server.json"; sleep 2
idle 60 "$OUT/srv-with.json"
server_stop
idle 60 "$OUT/srv-without-2.json"
echo "SRV done"; cat "$OUT"/srv-with*.json
