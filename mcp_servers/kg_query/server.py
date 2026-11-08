# -*- coding: utf-8 -*-
"""MCP 工具：知识图谱多跳查询。

这是"检索-推理双驱动"里"图检索"的那条腿，也是和朴素 RAG 拉开差距的关键工具。
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("kg-query")


@mcp.tool()
def find_entities(keyword: str, entity_type: str = "", limit: int = 10) -> list[dict]:
    """按关键词/类型查找实体节点。"""
    raise NotImplementedError


@mcp.tool()
def traverse_relations(start_entity: str, relation: str = "", hops: int = 2) -> list[dict]:
    """从起始实体出发做多跳关系遍历。

    Returns:
        [{"path": [n1, r1, n2, ...], "evidence": [{"file": "", "page": 0, "text": ""}]}]
    """
    raise NotImplementedError


@mcp.tool()
def compare_threshold(subject: str, operator: str, value: float, unit: str = "") -> list[dict]:
    """数值阈值比较，例如 eGFR=40 命中哪些"需减量/禁忌"条款。"""
    raise NotImplementedError


if __name__ == "__main__":
    mcp.run()
