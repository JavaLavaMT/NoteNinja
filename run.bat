@echo off
setlocal

set DIR=%~dp0

if not exist "%DIR%.venv" (
    echo Run setup.ps1 first.
    exit /b 1
)

call "%DIR%.venv\Scripts\activate.bat"
cd /d "%DIR%"

if "%1"=="pytest" (
    shift
    pytest %*
) else (
    python "%DIR%main.py" %*
)
