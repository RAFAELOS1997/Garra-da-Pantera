@echo off
set "APP_DIR=%~dp0"
if exist "%APP_DIR%.venv\Scripts\pythonw.exe" (
  "%APP_DIR%.venv\Scripts\pythonw.exe" "%APP_DIR%garra_da_pantera.py"
) else (
  py -3 "%APP_DIR%garra_da_pantera.py"
)
if errorlevel 1 pause
