@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 本程序通过真实MCP服务验收两跳、血压边界和适用范围比较。
echo 服务地址：http://127.0.0.1:8081/sse
python -X utf8 eval\run_reasoning_acceptance.py
echo.
echo 说明见 docs\08-三类推理是怎么做出来的.md
pause
