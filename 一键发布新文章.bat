@echo off
chcp 65001 >nul
color 0A
title 02687.com Auto Publisher
echo ==========================================
echo    02687.com 自动发布机器人启动中...
echo    正在调用 Gemini 大模型，请稍候...
echo ==========================================
cd /d "%~dp0"
python tools\auto_publish.py
echo.
echo ==========================================
echo    任务结束！按任意键关闭此窗口。
echo ==========================================
pause
