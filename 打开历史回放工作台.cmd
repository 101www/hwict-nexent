@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 历史回放：http://127.0.0.1:8766/ 与正式智能体隔离。
python -X utf8 tools\evolve_graph.py serve --port 8766
pause
