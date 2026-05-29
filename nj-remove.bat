@echo off
setlocal
set DIR=%~dp0

echo.
echo Stopping NoteNinja...
echo.

powershell -ExecutionPolicy Bypass -Command ^
    "Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq '' } | Stop-Process -Force -ErrorAction SilentlyContinue; ^
     $f = [System.Environment]::GetFolderPath('Startup') + '\NoteNinja.bat'; ^
     if (Test-Path $f) { Remove-Item $f; Write-Host 'Startup item removed.' } ^
     else { Write-Host 'No startup item found.' }"

echo.
echo Done. Run nj.bat to start NoteNinja again.
echo.
