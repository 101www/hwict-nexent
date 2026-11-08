"""保留 PDF 物理页和原文的分节器；不在此处修复表格或猜测阅读顺序。"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

PAGE = re.compile(r"^===== 第 (\d+) 页 =====\s*$")
HEADING = re.compile(r"^(\d{1,2}(?:\.\d+)*|[A-Z]\.\d+)\s+(.+)$")


def compact(text: str) -> tuple[str, list[int]]:
    """匹配时忽略排版空白，索引映射用于返回未经改写的原文。"""
    positions = [i for i, char in enumerate(text) if not char.isspace()]
    return "".join(text[i] for i in positions), positions


def source_span(block: dict, start: int, end: int) -> dict:
    _, offsets = compact(block["raw"])
    left, right = offsets[start], offsets[end - 1] + 1
    return {
        "file": block["file"], "section": block["section"],
        "page": block["page"], "block_id": block["id"],
        "start": left, "end": right, "evidence": block["raw"][left:right],
        "section_status": block.get("section_status", "unknown"),
        "verification": "pending", "confidence": 0.95,
        "confidence_basis": "rule_heuristic_not_calibrated",
    }


def load_blocks(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    blocks: list[dict] = []
    heading_titles: dict[str, str] = {}
    is_standard = "WS/T872" in compact(text[:5000])[0]

    def add(raw: str, section: str, title: str, chapter: str, page: int | None,
            source: str = "", legacy: bool = False) -> None:
        raw = raw.strip()
        if not raw:
            return
        ident = f"{path.name}|{len(blocks)}|{page}|{section}"
        blocks.append({"id": "B-" + hashlib.sha1(ident.encode()).hexdigest()[:12],
                       "file": path.name, "section": section, "title": title,
                       "chapter": chapter, "page": page, "raw": raw,
                       "body": raw.partition("【溯源】")[0], "source_text": source,
                       "legacy": legacy,
                       "verification": "pending", "confidence": 0.95,
                       "confidence_basis": "rule_heuristic_not_calibrated",
                       "section_status": "needs_layout_review" if is_standard and page in {4, 6}
                                         else "unknown" if section == "0" else "from_text_heading",
                       "heading_path": [heading_titles[prefix] for prefix in
                                        [".".join(section.split(".")[:i]) for i in range(1, len(section.split(".")) + 1)]
                                        if prefix in heading_titles]})

    if re.search(r"^【[^】]+/[^】]+】", text, re.M):
        # 兼容旧知识库摘要；它没有物理页标记，未知页用 null，绝不伪造第 1 页。
        for raw in re.split(r"\n\s*\n", text):
            match = re.match(r"^【([^】]+)】(.*)$", raw.strip(), re.S)
            chapter, section, title = "", "0", "文档元信息"
            if match:
                chapter, _, heading = match[1].partition("/")
                heading = heading.strip()
                numbered = HEADING.match(heading)
                section = numbered[1] if numbered else heading or chapter
                title = numbered[2] if numbered else ""
            source = raw.partition("【溯源】")[2].strip()
            add(raw, section, title, chapter.strip(), None, source, True)
        return blocks

    section, title, chapter, page = "0", "文档元信息", "", None
    # 这份专科期刊不是编号目录格式，避免把试验结果/图表数字误当章节号。
    numbered_layout = "中国高血压临床实践指南" not in compact(text[:5000])[0]
    lines: list[str] = []

    def flush() -> None:
        add("\n".join(lines), section, title, chapter, page)
        lines.clear()

    for line in text.splitlines():
        marker = PAGE.match(line)
        if marker:
            flush()
            page = int(marker[1])
            continue
        # 非编号的文后标题也会结束上一章节，不能把参考文献挂在附录 A.1 下。
        # 标题本身仍留在 raw 中；偏移始终指向未经改写的原文。
        if compact(line)[0] in {"参考文献", "References", "REFERENCES"}:
            flush()
            section, title, chapter = "REFERENCES", "参考文献", "参考文献"
            heading_titles[section] = title
        match = HEADING.match(line.strip())
        clinical_match = re.match(r"^临床问题\s*(\d+)\s*(.*)$", line.strip())
        if clinical_match and not numbered_layout:
            flush()
            section, title, chapter = "CQ" + clinical_match[1], clinical_match[2].strip(), "临床问题"
            heading_titles[section] = title
        if match and numbered_layout and section != "REFERENCES":
            candidate = match[2].strip()
            # 表格剂量、24 小时、1 mmHg 等不是章节标题。
            heading = (len(candidate) <= 110
                       and re.match(r"(?:[\u4e00-\u9fff]|[<≥]\s*80\s*岁)", candidate)
                       and not re.match(r"(?:小时|分钟|个月|次|片|克|岁|年|月|日)(?:\s|[，。])", candidate)
                       and (match[1].startswith("A.") or 1 <= int(match[1].split(".")[0]) <= 30))
            if heading:
                flush()
                section = match[1]
                title = re.split(r"[：:]", candidate, maxsplit=1)[0]
                heading_titles[section] = title
                if "." not in section:
                    chapter = title
        # 原文保留水印等噪声，匹配器按规则跳过，避免破坏证据偏移。
        lines.append(line)
    flush()
    return blocks
