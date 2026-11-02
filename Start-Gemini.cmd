@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "AI_PROVIDER=Gemini"
py -3.12 launch.py
pause
