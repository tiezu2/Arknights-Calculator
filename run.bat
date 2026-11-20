@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  start "" pyw app\app_desktop.py
) else (
  start "" pythonw app\app_desktop.py
)
