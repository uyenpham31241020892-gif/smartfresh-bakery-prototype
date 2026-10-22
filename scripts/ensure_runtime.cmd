@echo off
rem Shared dependency bootstrap. Called from the project root by both launchers.
set "SMARTFRESH_PYTHON="
if exist ".tools\python312\python.exe" goto portable
if exist ".venv\Scripts\python.exe" goto venv

echo [SmartFresh] Creating Python 3.12 environment...
py -3.12 -m venv .venv
if errorlevel 1 goto no_python
goto venv

:portable
set "SMARTFRESH_PYTHON=%CD%\.tools\python312\python.exe"
goto check

:venv
set "SMARTFRESH_PYTHON=%CD%\.venv\Scripts\python.exe"

:check
"%SMARTFRESH_PYTHON%" scripts\check_runtime.py >nul 2>nul
if not errorlevel 1 exit /b 0

echo [SmartFresh] Installing required libraries. Internet is needed on first start.
"%SMARTFRESH_PYTHON%" -m pip --version >nul 2>nul
if errorlevel 1 goto ensure_pip
goto install

:ensure_pip
"%SMARTFRESH_PYTHON%" -m ensurepip --upgrade
if errorlevel 1 goto install_failed

:install
"%SMARTFRESH_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto install_failed
"%SMARTFRESH_PYTHON%" scripts\check_runtime.py
if errorlevel 1 goto install_failed
exit /b 0

:no_python
echo.
echo [ERROR] Python 3.12 could not create the environment.
echo Install Python 3.12 with the Python Launcher, then run this file again.
exit /b 1

:install_failed
echo.
echo [ERROR] Dependencies could not be installed or loaded.
echo Check the errors above and your internet connection. The app has not started.
exit /b 1
