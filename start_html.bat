@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title YouTube Transcribe Downloader

:: One click: start the local page and open it in your browser.
:: First run installs what is needed (same as run_transcript_v2.bat).
if not exist ".venv\Scripts\python.exe" (
  call run_transcript_v2.bat
  if errorlevel 1 pause & exit /b 1
)
if not exist ".venv\.fix_v4" (
  ".venv\Scripts\python.exe" -m pip install youtube-transcript-api >nul 2>&1
  echo done> ".venv\.fix_v4"
)
set "PY=.venv\Scripts\python.exe"
set "PATH=%~dp0.venv\Scripts;%PATH%"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
start "" http://127.0.0.1:8765/
"%PY%" server.py
pause
