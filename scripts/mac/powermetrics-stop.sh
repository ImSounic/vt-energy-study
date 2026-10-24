#!/usr/bin/env bash
# Stops any running powermetrics started by powermetrics-start.sh (never prompts).
sudo -n pkill -x powermetrics || true
sleep 1
