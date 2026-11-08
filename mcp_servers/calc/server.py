# -*- coding: utf-8 -*-
"""MCP 工具：领域数值计算（剂量/额度/评分等）。推理链里"不能靠模型心算"的部分。"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("domain-calc")


@mcp.tool()
def compute(expression: str) -> dict:
    """安全表达式计算，返回结果与计算过程。"""
    raise NotImplementedError


if __name__ == "__main__":
    mcp.run()
