# -*- coding: utf-8 -*-
"""朴素 RAG 基线。作用：给评委一个"我们比普通做法强多少"的对照。

设计：单跳向量检索 + 一次生成，无图谱、无多跳、无引用回填。
"""
from __future__ import annotations


def build_index(chunks_path: str) -> None:
    """TODO: 建向量索引（本地可用 sentence-transformers / 云端用 MaaS embedding）。"""
    raise NotImplementedError


def answer(question: str, top_k: int = 5) -> dict:
    """TODO: 检索 top_k 段 → 拼 prompt → 生成。不返回引用。"""
    raise NotImplementedError


def run_eval(dataset_path: str) -> dict:
    """TODO: 跑全量评测集，返回 {"accuracy": ..., "citation_hit": ...}。"""
    raise NotImplementedError
