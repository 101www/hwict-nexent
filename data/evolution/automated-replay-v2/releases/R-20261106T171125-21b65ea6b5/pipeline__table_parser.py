# -*- coding: utf-8 -*-
"""表格结构还原。表格是多模态里最容易被做丢的部分，也是数值推理的前提。"""


def parse_table(path: str) -> list[dict]:
    """TODO: 还原为 {page, caption, headers, rows}，并把每行转成可检索文本。"""
    raise NotImplementedError


def table_to_chunks(table: dict, file_name: str) -> list[dict]:
    """表格 → chunk：每行生成"表头: 值"的句子化文本，便于检索与图抽取。"""
    chunks = []
    headers = table.get("headers", [])
    for i, row in enumerate(table.get("rows", [])):
        sentence = "；".join(f"{h}: {v}" for h, v in zip(headers, row) if v not in (None, ""))
        chunks.append(
            {
                "chunk_id": f"{file_name}-t{i}",
                "text": f"[表格] {table.get('caption', '')} {sentence}",
                "meta": {"file": file_name, "page": table.get("page", 1), "type": "table"},
            }
        )
    return chunks
