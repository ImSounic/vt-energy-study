#!/usr/bin/env bash
# Stops any running powermetrics started by powermetrics-start.sh.
sudo pkill -x powermetrics || true
sleep 1
