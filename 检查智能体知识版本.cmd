@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -X utf8 tools\check_live_connection.py
pause
