@echo off
setlocal
set DIR=%~dp0
powershell -ExecutionPolicy Bypass -Command ^
    "$f = [System.Environment]::GetFolderPath('Startup') + '\NoteNinja.bat'; ^
     if (Test-Path $f) { Remove-Item $f; Write-Host 'Removed NoteNinja from startup.' } ^
     else { Write-Host 'NoteNinja not found in startup (already removed?).' }"
