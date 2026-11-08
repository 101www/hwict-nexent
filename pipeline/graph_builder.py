# -*- coding: utf-8 -*-
"""chunk → 知识图谱。原则：图上每一条边都必须能指回 (file, page)。"""
from __future__ import annotations

import json
from pathlib import Path


def load_chunks(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_candidates(chunk: dict, schema_path: Path, llm) -> dict:
    """按 ontology/extraction_prompt.md 调用 LLM 抽取候选实体/关系。

    llm: 任意 OpenAI 兼容客户端；开发期可用本地模型，正式期可切华为云 MaaS。
    """
    prompt = schema_path.read_text(encoding="utf-8")
    # TODO: 拼接 chunk 与现有本体，调用 LLM，解析 JSON，校验 evidence 可定位
    raise NotImplementedError


def build_graph(chunks: list[dict], out_path: Path) -> None:
    """TODO: 写入图存储（Neo4j / 轻量属性图 / 关系型三元组表均可，重点是能多跳）。"""
    raise NotImplementedError


def traverse(seed: str, hops: int = 3) -> list[dict]:
    """多跳遍历 —— 赛题"跨文档多跳推理"的核心算子。返回路径及每条边的出处。"""
    raise NotImplementedError
