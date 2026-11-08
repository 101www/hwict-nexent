@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正式版本工作台：http://127.0.0.1:8765/
echo 审核发布后，跟随正式仓库的MCP在下一次工具调用生效。
python -X utf8 tools\evolve_graph.py --production serve
pause
