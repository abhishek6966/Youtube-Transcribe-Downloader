@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title YouTube Transcript Generator

:: If the private environment already exists, just use it
if exist ".venv\Scripts\python.exe" goto :ready

:: ---- find a compatible Python (3.12 / 3.13 / 3.11), side by side with 3.14 ----
:findpy
set "BASEPY="
py -3.12 --version >nul 2>&1 && set "BASEPY=py -3.12"
if not defined BASEPY ( py -3.13 --version >nul 2>&1 && set "BASEPY=py -3.13" )
if not defined BASEPY ( py -3.11 --version >nul 2>&1 && set "BASEPY=py -3.11" )
if defined BASEPY goto :makevenv

if defined TRIED_WINGET goto :nopython
set "TRIED_WINGET=1"
echo Python 3.12 not found. Installing it alongside your other Python ^(nothing is removed^)...
where winget >nul 2>&1
if errorlevel 1 goto :nopython
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
goto :findpy

:nopython
echo.
echo Could not find or install Python 3.12 automatically.
echo Please install it manually - it will NOT remove your Python 3.14:
echo   https://www.python.org/downloads/release/python-3120/
echo Then run this file again.
pause
exit /b 1

:makevenv
echo Creating private environment with %BASEPY% ...
%BASEPY% -m venv .venv
if errorlevel 1 (
    echo Failed to create environment.
    rmdir /s /q .venv >nul 2>&1
    pause
    exit /b 1
)
echo Installing required packages ^(first run only, may take a few minutes^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
".venv\Scripts\python.exe" -m pip install "av>=14,<16" faster-whisper unidecode "yt-dlp[default]" pykakasi pypinyin korean-romanizer youtube-transcript-api
".venv\Scripts\python.exe" -m pip install deno >nul 2>&1
echo done> ".venv\.fix_v2"
echo done> ".venv\.fix_v3"
echo done> ".venv\.fix_v4"
if errorlevel 1 (
    echo.
    echo Package install failed. Check your internet connection and try again.
    rmdir /s /q .venv >nul 2>&1
    pause
    exit /b 1
)

:ready
set "PY=.venv\Scripts\python.exe"
set "PATH=%~dp0.venv\Scripts;%PATH%"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

:: one-time repair for setups made by an older version of this file
if not exist ".venv\.fix_v2" (
    echo Applying one-time fix ^(compatible audio decoder + JavaScript runtime^)...
    "%PY%" -m pip install "av>=14,<16" "yt-dlp[default]" --upgrade
    "%PY%" -m pip install deno >nul 2>&1
    echo done> ".venv\.fix_v2"
)
if not exist ".venv\.fix_v3" (
    echo Installing extra romanizers for Japanese, Chinese and Korean...
    "%PY%" -m pip install pykakasi pypinyin korean-romanizer
    echo done> ".venv\.fix_v3"
)

if not exist ".venv\.fix_v4" (
    echo Installing captions library for v2 ^(instant captions first^)...
    "%PY%" -m pip install youtube-transcript-api
    echo done> ".venv\.fix_v4"
)

:ask
echo.
echo ==========================================================
echo   YouTube Transcript Generator v2  (captions first, turbo)
echo ==========================================================
set "LINK="
set /p "LINK=Paste YouTube video link (or press Enter to quit): "
if not defined LINK goto :end

set "YT_LANG="
set /p "YT_LANG=Language code like es, hi, ja - or just press Enter to auto-detect: "

echo.
echo Working... captions take seconds; only if there are none does it transcribe audio.
"%PY%" yt_transcript_v2.py "%LINK%"
if errorlevel 1 (
    echo.
    echo Something went wrong. See the message above.
    goto :again
)

:: ---- open the newest saved transcript ----
set "NEWEST="
for /f "delims=" %%F in ('dir /b /o-d "transcripts\*.txt" 2^>nul') do (
    set "NEWEST=%%F"
    goto :found
)
:found
if defined NEWEST (
    echo.
    echo Transcript saved in: %~dp0transcripts\
    start "" notepad "%~dp0transcripts\%NEWEST%"
    start "" explorer "%~dp0transcripts"
)

:again
echo.
set "MORE="
set /p "MORE=Do another video? (Y/N): "
if /i "%MORE%"=="Y" goto :ask

:end
endlocal
