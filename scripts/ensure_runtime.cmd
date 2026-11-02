@echo off
set "SMARTFRESH_PYTHON=%CD%\.venv\Scripts\python.exe"
if exist "%SMARTFRESH_PYTHON%" exit /b 0
py -3.12 -m venv .venv
exit /b %errorlevel%
