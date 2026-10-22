@echo off
chcp 65001 >nul
cd /d "%~dp0"
call scripts\ensure_runtime.cmd
if errorlevel 1 goto done
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_ollama.ps1
"%SMARTFRESH_PYTHON%" app.py
:done
pause
