@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run Open_Transcriber.bat first, then close the studio.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-maximum.txt
if errorlevel 1 echo Installation did not complete. Basic studio still available if dependencies remain compatible.
pause
