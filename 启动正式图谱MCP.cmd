@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 保持此窗口运行，Nexent通过8081端口访问工具。
python -X utf8 tools\evolve_graph.py --production launch-java
pause
