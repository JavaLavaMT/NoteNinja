@echo off
setlocal

set DIR=%~dp0

if not exist "%DIR%.venv" (
    echo First run detected — starting setup...
    powershell -ExecutionPolicy Bypass -File "%DIR%setup.ps1"
)

call "%DIR%.venv\Scripts\activate.bat"
cd /d "%DIR%"

if "%1"=="pytest" (
    shift
    pytest %*
) else if "%1"=="menubar" (
    pythonw "%DIR%menubar.py"
) else if "%1"=="logs" (
    set LOG=%USERPROFILE%\.noteninja.log
    if not exist "%LOG%" (
        echo No log file yet — run NoteNinja first.
    ) else (
        powershell -Command "Get-Content '%USERPROFILE%\.noteninja.log' -Wait"
    )
) else (
    python "%DIR%main.py" %*
)
