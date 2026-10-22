@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Start without launching a local Ollama model.
call scripts\ensure_runtime.cmd
if errorlevel 1 goto done
"%SMARTFRESH_PYTHON%" app.py
:done
pause
