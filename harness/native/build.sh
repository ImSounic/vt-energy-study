#!/usr/bin/env bash
# Builds the IOReport shim used by IoReportReader (macOS only) and runs its
# smoke test. Output: harness/native/libioreport_shim.dylib
set -euo pipefail
cd "$(dirname "$0")"
clang -O2 -Wall -dynamiclib -o libioreport_shim.dylib ioreport_shim.c \
  -framework CoreFoundation -lIOReport
clang -O2 -Wall -o shim_smoke shim_smoke.c ioreport_shim.c \
  -framework CoreFoundation -lIOReport
./shim_smoke
