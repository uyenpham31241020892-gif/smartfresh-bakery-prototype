@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_ollama.ps1
if exist ".tools\python312\python.exe" (
  ".tools\python312\python.exe" app.py
  goto done
)
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Please install Python 3.12, then run Start.cmd again.
    goto done
  )
)
".venv\Scripts\python.exe" -c "import fastapi, lightgbm, pandas, httpx, openpyxl" >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto done
)
".venv\Scripts\python.exe" app.py
:done
pause
