@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Start SmartFresh without starting a local Ollama model (useful on 4 GB RAM laptops).
if exist ".tools\python312\python.exe" (
  ".tools\python312\python.exe" app.py
  goto done
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
  goto done
)
py -3.12 app.py
:done
pause
