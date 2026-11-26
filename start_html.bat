@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title Universal Transcription Studio
if not exist ".venv\Scripts\python.exe" (
  py -3.12 --version >nul 2>&1
  if errorlevel 1 (
    echo Python 3.12 is required for the computer package.
    echo Install it from https://www.python.org/downloads/ then run again.
    pause
    exit /b 1
  )
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Could not create the private environment.
    pause
    exit /b 1
  )
)
if not exist ".venv\.studio_v1" (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Setup failed. Check the internet connection and run again.
    pause
    exit /b 1
  )
  echo ready>".venv\.studio_v1"
)
set "PATH=%~dp0.venv\Scripts;%PATH%"
".venv\Scripts\python.exe" server.py --open
pause
