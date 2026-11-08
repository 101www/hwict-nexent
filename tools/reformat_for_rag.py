# -*- coding: utf-8 -*-
"""把结构化文档重排成对 RAG 友好的形式。

背景
----
Nexent v2.7.0 的知识库不支持自定义分片参数，默认按字符数硬切，
会把「小节」和「知识溯源」切散 —— 而溯源是赛题的核心要求。

既然切分器改不了，就改喂给它的文档：
让「小节边界」变成「段落边界」，默认切分器就会按小节切。

产出
----
1. <原名>_重排.txt   小节之间留空行，标题独立成段；每段自带章节标题 + 溯源
2. split/            每个小节一个独立文件（最保险：一文件 = 一 chunk）

用法
----
    python reformat_for_rag.py "中国高血压临床实践指南2025版_知识库文档.txt"

    # 也可指定输出目录
    python reformat_for_rag.py input.txt -o out
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Windows 控制台默认 GBK，直接打印 ✅/❌ 会抛 UnicodeEncodeError，统一切到 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# 章节：一、二、三、……  十、十一、……
CHAPTER_RE = re.compile(r"^([一二三四五六七八九十]+)、\s*(.+)$")
# 小节：1.1 / 2.3 / 10.2
SECTION_RE = re.compile(r"^(\d+\.\d+)\s+(.+)$")
# 溯源块起始标记
TRACE_MARK = "知识溯源"


def parse_structured(text: str) -> tuple[list[dict], list[str]]:
    """把文档解析成 [{title, sections:[{no,name,body}], traces:[...]}]。

    返回 (chapters, preface)；preface 是第一个章节之前的元信息。
    """
    chapters: list[dict] = []
    preface: list[str] = []
    ch: dict | None = None
    sec: dict | None = None
    in_trace = False

    for raw in text.splitlines():
        line = raw.rstrip()

        m = CHAPTER_RE.match(line)
        if m:
            ch = {"title": line, "sections": [], "traces": []}
            chapters.append(ch)
            sec, in_trace = None, False
            continue

        if ch is None:
            preface.append(line)
            continue

        if line.strip() == TRACE_MARK:
            in_trace, sec = True, None
            continue

        m = SECTION_RE.match(line)
        if m and not in_trace:
            sec = {"no": m.group(1), "name": m.group(2), "body": []}
            ch["sections"].append(sec)
            continue

        if in_trace:
            if line.strip():
                ch["traces"].append(line.strip())
        elif sec is not None:
            sec["body"].append(line)
        else:
            # 章节标题之后、第一个小节之前的内容（如「1.1」缺失时的引言）
            ch["sections"].append({"no": "", "name": "", "body": [line]})
            sec = ch["sections"][-1]

    return chapters, preface


def _clean(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def build_blocks(chapters: list[dict], preface: list[str]) -> list[tuple[str, str]]:
    """产出 [(文件名, 块文本)]，每块 = 一个小节 + 该章节的溯源。

    关键：块**内部不留空行**，标题 / 正文 / 溯源用单换行连接。
    这样「块与块之间」才是唯一的段落边界，切分器只会在块之间切，
    不会把「正文」和「溯源」切开。
    """
    blocks: list[tuple[str, str]] = []

    pre = _clean(preface)
    if pre:
        blocks.append(("00_文档元信息", pre.replace("\n", " ")))

    for ci, ch in enumerate(chapters, start=1):
        # 前言（章节标题之后、第一个小节之前的内容）
        intro = " ".join(
            ln.strip()
            for sec in ch["sections"] if not sec["no"]
            for ln in sec["body"] if ln.strip()
        )
        trace_inline = " ".join(t.strip() for t in ch["traces"])

        for sec in ch["sections"]:
            body = _clean(sec["body"]).replace("\n", " ")
            if not body and not sec["no"]:
                continue

            head = ch["title"] if not sec["no"] else f'{ch["title"]} / {sec["no"]} {sec["name"]}'
            lines = [f"【{head}】"]
            if intro and not sec["no"]:
                lines.append(intro)
            if body:
                lines.append(body)
            if trace_inline:
                lines.append(f"【溯源】{trace_inline}")

            name = f'{ci:02d}-{sec["no"] or "0"}_{sec["name"] or "概述"}'
            blocks.append((name, "\n".join(lines)))

    return blocks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="输入文件（.txt / .md）")
    ap.add_argument("-o", "--outdir", default=None, help="输出目录（默认与输入同目录）")
    args = ap.parse_args()

    src = Path(args.input)
    text = src.read_text(encoding="utf-8")
    outdir = Path(args.outdir) if args.outdir else src.parent
    outdir.mkdir(parents=True, exist_ok=True)

    chapters, preface = parse_structured(text)
    blocks = build_blocks(chapters, preface)

    if not blocks:
        print("❌ 没解析出任何内容，请检查文档的章节格式（一、/ 1.1）")
        return

    # 产出 1：单文件重排版
    merged = "\n\n\n".join(b for _, b in blocks)
    merged_path = outdir / f"{src.stem}_重排.txt"
    merged_path.write_text(merged, encoding="utf-8")

    # 产出 2：每小节一个文件
    split_dir = outdir / "split"
    split_dir.mkdir(exist_ok=True)
    for name, block in blocks:
        (split_dir / f"{name}.txt").write_text(block, encoding="utf-8")

    print(f"✅ 解析出 {len(chapters)} 个章节 / {len(blocks)} 个知识块")
    print(f"   单文件重排版：{merged_path}")
    print(f"   分文件版    ：{split_dir}\\  （{len(blocks)} 个文件）")
    print()
    print("建议先传「单文件重排版」；如果还是切得不好，再传 split/ 里的文件。")


if __name__ == "__main__":
    main()
