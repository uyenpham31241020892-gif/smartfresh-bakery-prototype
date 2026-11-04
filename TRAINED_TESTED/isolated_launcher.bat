@echo off
setlocal enabledelayedexpansion

REM ==============================================================================
REM CẤU HÌNH CÁCH LY QUYỀN FILESYSTEM GIỮA CUSTODIAN VÀ MODEL AGENT (WINDOWS)
REM ==============================================================================
set "WORKSPACE_ROOT=%cd%"
set "RUNTIME_DIR=%WORKSPACE_ROOT%\03_TEST_POS_RUNTIME"
set "CUSTODIAN_DIR=%WORKSPACE_ROOT%\01_ORIGINAL_BASELINE_PRIVATE"
set "FROZEN_ZIP=%WORKSPACE_ROOT%\TRAINED_MODELS_FROZEN.zip"
set "AGENT_WORK_DIR=%WORKSPACE_ROOT%\agent_sandbox"

echo [1/4] Giai nen goi model da khoa vao vung sandbox cua Agent...
if not exist "%AGENT_WORK_DIR%" mkdir "%AGENT_WORK_DIR%"
python -m zipfile -e "%FROZEN_ZIP%" "%AGENT_WORK_DIR%"

echo [2/4] Kiem tra cach ly: Dam bao thu muc Custodian khong nam trong AGENT_WORK_DIR...

echo [3/4] Chay kiem tra tich hop tren Fixture/Development truoc khi mo Test...
python run_official_test_62days.py --mode SMOKE_DEV --runtime-dir "%RUNTIME_DIR%" --agent-dir "%AGENT_WORK_DIR%"
if %errorlevel% neq 0 (
    echo [ERROR] Smoke Dev test failed!
    exit /b %errorlevel%
)

echo [4/4] Khoi chay danh gia chinh thuc 62 ngay (01/07/2022 - 31/08/2022) cho 4 nhanh...
python run_official_test_62days.py --mode OFFICIAL_FROZEN_TEST --runtime-dir "%RUNTIME_DIR%" --custodian-dir "%CUSTODIAN_DIR%" --agent-dir "%AGENT_WORK_DIR%" --output-dir "%WORKSPACE_ROOT%\test_deliverables_v610"

endlocal
