#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec python3 code/pos_server.py --runtime-dir . --custodian-dir ../01_ORIGINAL_BASELINE_PRIVATE --mode DEMO --scorer-output ../01_ORIGINAL_BASELINE_PRIVATE/demo_run_results
