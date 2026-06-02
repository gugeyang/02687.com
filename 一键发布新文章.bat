@echo off
rem ============================================================
rem  02687.com one-click auto publish
rem  NOTE: keep this .bat ASCII-only. cmd.exe miscounts bytes of
rem  multibyte (Chinese) chars under chcp 65001 and breaks lines.
rem  chcp 65001 is still needed so the script's UTF-8 logs show.
rem ============================================================
chcp 65001 >nul
color 0A
title 02687.com Auto Publisher

cd /d "%~dp0"

rem Use the Python that actually has the deps (google-genai, requests).
set "PY=%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
if not exist "%PY%" set "PY=py -3.9"

echo ============================================================
echo   02687.com Auto Publisher
echo ------------------------------------------------------------
echo   Double-click   = auto pick next topic from DEVELOPMENT_PLAN
echo   Manual topic   = run in CMD:  %~nx0 "your topic here"
echo   Preview only   = add  --dry-run
echo   Skip review    = add  --skip-review
echo ============================================================
echo.

"%PY%" tools\auto_publish.py %*

echo.
echo ============================================================
echo   Done. Press any key to close...
echo ============================================================
pause >nul
