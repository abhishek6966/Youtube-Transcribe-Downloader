@echo off
:: Double-click this file to open the app the RIGHT way.
:: It starts the small local server and opens the page from it,
:: so API keys can connect. (Opening Transcript.html directly with a
:: double-click does NOT work for API keys — browsers block it.)
cd /d "%~dp0"
call start_html.bat
