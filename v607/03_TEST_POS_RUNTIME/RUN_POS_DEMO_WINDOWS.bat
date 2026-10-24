@echo off
cd /d "%~dp0"
python code\pos_server.py --runtime-dir . --custodian-dir "..\01_ORIGINAL_BASELINE_PRIVATE" --mode DEMO --scorer-output "..\01_ORIGINAL_BASELINE_PRIVATE\demo_run_results"
pause
