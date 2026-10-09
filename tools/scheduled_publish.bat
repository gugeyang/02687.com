@echo off
rem ============================================================
rem  02687.com unattended publish (run by Windows Task Scheduler)
rem  Same as the one-click .bat but with no pause and output
rem  appended to logs\scheduled_publish.log. Keep ASCII-only.
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0.."
if not exist logs mkdir logs
set "PYTHONIOENCODING=utf-8"
set "PY=%LOCALAPPDATA%\Programs\Python\Python39\python.exe"

echo. >> logs\scheduled_publish.log
echo ===== %DATE% %TIME% ===== >> logs\scheduled_publish.log
"%PY%" -W ignore::FutureWarning tools\auto_publish.py >> logs\scheduled_publish.log 2>&1
echo ===== exit code %ERRORLEVEL% ===== >> logs\scheduled_publish.log
