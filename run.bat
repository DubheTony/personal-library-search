@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [setup] creating virtual environment and installing PySide6...
    python -m venv .venv
    if errorlevel 1 goto failed
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt --index-url https://pypi.org/simple
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 goto failed
goto end

:failed
echo.
echo [error] Startup failed. See the message above.
pause

:end
endlocal
