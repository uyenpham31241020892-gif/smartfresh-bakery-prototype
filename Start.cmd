@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "SMARTFRESH_PYTHON=%CD%\.tools\python312\python.exe"
if not exist "%SMARTFRESH_PYTHON%" set "SMARTFRESH_PYTHON=python"
"%SMARTFRESH_PYTHON%" -c "import sklearn,xgboost,pandas,joblib; assert sklearn.__version__=='1.8.0'; assert xgboost.__version__=='3.1.3'" >nul 2>nul
if errorlevel 1 (
  "%SMARTFRESH_PYTHON%" -m pip install -r v606\requirements.txt
  if errorlevel 1 goto done
)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_ollama.ps1
"%SMARTFRESH_PYTHON%" app.py
:done
pause
