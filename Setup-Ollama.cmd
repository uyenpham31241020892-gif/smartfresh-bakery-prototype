@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run Start.cmd once before this setup.& pause & exit /b 1)
".venv\Scripts\python.exe" scripts\setup_ollama.py
pause
