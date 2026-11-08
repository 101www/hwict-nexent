# -*- coding: utf-8 -*-
"""多模态数据资产统一识别入口：文件 → 带元数据的 chunk 列表。

设计要点（评委关注）：每个 chunk 必须携带 file / page / section / type，
否则"决策链路可溯源"无法实现。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class Chunk:
    chunk_id: str
    text: str
    meta: dict = field(default_factory=dict)
    # meta 约定字段: file, page, section, type(text|table|figure), asset_tags


def _make_id(source: str, page: int, offset: int, text: str) -> str:
    raw = f"{source}|{page}|{offset}|{text[:64]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def ingest_text(path: Path, page: int = 1, section: str = "") -> list[Chunk]:
    """纯文本 / 已抽好文字层的 PDF → chunk。"""
    chunks: list[Chunk] = []
    for offset, para in enumerate(_split_paragraphs(path.read_text(encoding="utf-8"))):
        chunks.append(
            Chunk(
                chunk_id=_make_id(str(path), page, offset, para),
                text=para,
                meta={"file": path.name, "page": page, "section": section, "type": "text"},
            )
        )
    return chunks


def _split_paragraphs(text: str, max_len: int = 800) -> list[str]:
    paras, buf = [], ""
    for line in text.splitlines():
        if not line.strip():
            if buf.strip():
                paras.append(buf.strip())
            buf = ""
            continue
        buf += line + "\n"
        if len(buf) >= max_len:
            paras.append(buf.strip())
            buf = ""
    if buf.strip():
        paras.append(buf.strip())
    return paras


def pdf_pages(path: Path) -> list[tuple[int, str]]:
    """PDF → [(页码, 文本), ...]。优先 pdfminer.six（中文版面处理好），退回 PyPDF2。

    只认【有文字层】的 PDF。扫描件抽出来是空的 —— 这里会显式报错，
    而不是静默返回空串，否则下游会误判成"这份文档没内容"。
    """
    path = Path(path)
    pages: list[tuple[int, str]] = []
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.pdfpage import PDFPage

        with path.open("rb") as fh:
            total = len(list(PDFPage.get_pages(fh)))
        for i in range(total):
            pages.append((i + 1, (extract_text(str(path), page_numbers=[i]) or "").strip()))
    except Exception:  # noqa: BLE001 —— 换 PyPDF2 兜底
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        pages = [(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]

    if not any(t for _, t in pages):
        raise ValueError(
            f"{path.name}: 未抽到任何文字层，极可能是扫描件 —— 需先走 pipeline/ocr.py 再抽取"
        )
    return pages


def ingest_pdf(path: Path) -> list[Chunk]:
    """有文字层的 PDF → chunk。每页单独标 page，保证引用能定位到页。"""
    chunks: list[Chunk] = []
    for page, text in pdf_pages(path):
        if not text:
            continue
        for offset, para in enumerate(_split_paragraphs(text)):
            chunks.append(
                Chunk(
                    chunk_id=_make_id(str(path), page, offset, para),
                    text=para,
                    meta={"file": path.name, "page": page, "section": "", "type": "text"},
                )
            )
    return chunks


def ingest_table(path: Path) -> list[Chunk]:
    """TODO: XLSX/CSV → 结构化 chunk，表格需保留表头语义。"""
    raise NotImplementedError


def ingest_image(path: Path) -> list[Chunk]:
    """TODO: 图表/流程图 → 多模态模型生成结构化描述。"""
    raise NotImplementedError


def ingest_dir(root: Path, out: Path) -> None:
    """批量处理目录并按 JSONL 落盘，供 graph_builder 与知识库导入使用。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                if path.suffix.lower() in {".txt", ".md"}:
                    chunks = ingest_text(path)
                elif path.suffix.lower() == ".pdf":
                    chunks = ingest_pdf(path)
                elif path.suffix.lower() in {".xlsx", ".csv"}:
                    chunks = ingest_table(path)
                elif path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    chunks = ingest_image(path)
                else:
                    continue
            except NotImplementedError:
                print(f"[skip] 未实现: {path.name}")
                continue
            for c in chunks:
                f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
                n += 1
    print(f"写出 {n} 个 chunk -> {out}")


if __name__ == "__main__":
    import sys

    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = sys.argv[1:]
    if args and args[0] == "--pdf":
        # 单份 PDF → 带页码的纯文本，供 reformat / build_graph 使用
        src = Path(args[1])
        dst = Path(args[3]) if len(args) > 3 and args[2] == "--out" else src.with_suffix(".txt")
        pages = pdf_pages(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("w", encoding="utf-8") as f:
            for page, text in pages:
                f.write(f"\n===== 第 {page} 页 =====\n{text}\n")
        total = sum(len(t) for _, t in pages)
        print(f"抽出 {len(pages)} 页 / {total} 字 -> {dst}")
    else:
        ingest_dir(Path("data/raw"), Path("data/processed/chunks.jsonl"))
