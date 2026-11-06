@echo off
set "mrpPython=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%mrpPython%" (
  "%mrpPython%" "%~dp0web_server.py" --open-browser
) else (
  python "%~dp0web_server.py" --open-browser
)
pause
