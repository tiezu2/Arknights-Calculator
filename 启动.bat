@echo off
chcp 65001 >nul
title 明日方舟练度计算器 V01.0
cd /d "%~dp0"
if exist "明日方舟练度计算器V01.0.exe" (
  start "" "明日方舟练度计算器V01.0.exe"
  exit /b
)
if exist "明日方舟培养终端.exe" (
  start "" "明日方舟培养终端.exe"
  exit /b
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw app\app_desktop.py
) else (
  echo 未找到程序，请确认 exe 还在本目录
  pause
)
