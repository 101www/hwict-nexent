#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版面感知的 PDF 文本抽取 —— 专治双栏期刊排版。

【为什么需要它】
期刊 PDF 是双栏排版。pdfminer 默认按"从上到下扫一遍"读，会交替吐出
左栏第 3 行、右栏第 3 行，结果句子被切碎：

    ·高血压前期及高血压患者心血管危险分层划分为
    10~15
    年间进展为高血压［
    ，
    32
    ］。若

这类输入交给下游，抽取规则一条都命中不了 —— 不是图谱的问题，是**输入就烂了**。
这就是赛题强调"多模态复杂版面"的真实含义。

【做法】
  1. 用 pdfminer 的 layout 分析拿到每一【行】的包围盒 (x0,y0,x1,y1)
  2. 按横向位置把行分成三类：跨栏 S / 左栏 L / 右栏 R
  3. 输出顺序：顶部跨栏(标题摘要) → 左栏自上而下 → 右栏自上而下 → 其余跨栏
  4. 没有右栏内容的页面按单栏处理（如 8 页的 WS/T 标准）

【已知局限】
栏区内部的跨栏元素（宽表格、图注）会被排到页尾。文本为主的期刊影响很小，
但表格类文档需要 pipeline/table_parser.py 单独处理。

用法：
    python pipeline/pdf_layout.py --pdf <输入.pdf> --out <输出.txt> [--report]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 判定"骑跨中线"的容差：占页宽的比例
SPAN_TOL_RATIO = 0.06


def _page_lines(page_layout) -> list[dict]:
    """把 pdfminer 的页面布局对象拍平成 [{text, x0, x1, y0, y1}, ...]。"""
    from pdfminer.layout import LTTextContainer, LTTextLine

    out: list[dict] = []
    for el in page_layout:
        if not isinstance(el, LTTextContainer):
            continue
        for line in el:
            if not isinstance(line, LTTextLine):
                continue
            txt = line.get_text().strip()
            if not txt:
                continue
            out.append({
                "text": txt,
                "x0": float(line.x0), "x1": float(line.x1),
                "y0": float(line.y0), "y1": float(line.y1),
            })
    return out


def _cluster_lines(lines: list[dict]) -> list[dict]:
    """把视觉上属于同一行的碎片合并成一行。

    【为什么不能只按 y 聚类】
    实测这份期刊：同一视觉行里，中文与西文的字框**垂直错位 7.7pt**，而行距只有 15.9pt。

        y0=734.53  目 前 尚 无 测 量 血 压 前 休 息     ← 中文
        y0=726.82                    3~5 min         ← 西文，整体下沉 7.7pt
        y0=718.65  比较的直接证据，但一项               ← 中文，下一行

    按中心距 8pt 聚类会踩在临界点上，飘忽不定。

    【正确判据】
    再加一条硬约束：**同一视觉行的碎片在 x 方向上永不重叠**（它们首尾相接）。
    不同行的碎片几乎总会重叠。两条一起用，判据就稳了：
        |中心距| ≤ 0.9×字高   且   x 区间与已收碎片不重叠  →  同一行
    """
    if not lines:
        return []

    def center(l: dict) -> float:
        return (l["y0"] + l["y1"]) / 2.0

    heights = sorted(l["y1"] - l["y0"] for l in lines)
    h = heights[len(heights) // 2] or 10.0
    y_tol, x_slack = h * 0.9, 2.0

    clusters: list[dict] = []
    for ln in sorted(lines, key=lambda l: (-center(l), l["x0"])):
        c = center(ln)
        target = None
        for cl in clusters:                       # 已按中心自上而下排列
            if abs(c - cl["c"]) > y_tol:
                continue
            overlapped = any(
                not (ln["x1"] <= a + x_slack or ln["x0"] >= b - x_slack)
                for a, b in cl["spans"]
            )
            if overlapped:
                continue
            target = cl
            break
        if target is None:
            clusters.append({"c": c, "spans": [(ln["x0"], ln["x1"])], "parts": [ln]})
        else:
            target["parts"].append(ln)
            target["spans"].append((ln["x0"], ln["x1"]))
            target["c"] = sum(center(p) for p in target["parts"]) / len(target["parts"])

    clusters.sort(key=lambda cl: -cl["c"])
    merged: list[dict] = []
    for cl in clusters:
        parts = sorted(cl["parts"], key=lambda l: l["x0"])
        text, prev_x1 = "", None
        for p in parts:
            if prev_x1 is not None and p["x0"] - prev_x1 > 2.0:
                text += " "
            text += p["text"]
            prev_x1 = p["x1"] if prev_x1 is None else max(prev_x1, p["x1"])
        merged.append({"text": text.strip()})
    return merged


def read_page(page_layout) -> tuple[str, dict]:
    """单页 → (重排后的文本, 本页统计)。"""
    w, h = float(page_layout.width), float(page_layout.height)
    lines = _page_lines(page_layout)
    stat = {"lines": len(lines), "cols": 1}
    if not lines:
        return "", stat

    mid, tol = w / 2.0, w * SPAN_TOL_RATIO
    for ln in lines:
        if ln["x0"] < mid - tol and ln["x1"] > mid + tol:
            ln["col"] = "S"                      # 横跨中线：标题/摘要/宽表
        elif ln["x1"] <= mid:
            ln["col"] = "L"
        elif ln["x0"] >= mid:
            ln["col"] = "R"
        else:
            ln["col"] = "S"

    left = [l for l in lines if l["col"] == "L"]
    right = [l for l in lines if l["col"] == "R"]
    span = [l for l in lines if l["col"] == "S"]

    # 单栏守卫：只有当左右两侧【各自】都占到足够比例的行时，才认定是双栏。
    # 否则像 WS/T 标准这种单栏公文，只要有几个缩进的行被误判成"右栏"，
    # 整页顺序就会被打乱（这是实测踩到的坑）。
    enough = 0.25 * len(lines)
    if len(left) < enough or len(right) < enough:
        merged = _cluster_lines(lines)
        stat["rows"] = len(merged)
        return "\n".join(m["text"] for m in merged), stat

    stat["cols"] = 2
    y_top = max(l["y1"] for l in left + right)      # 栏区的最高点
    above = [l for l in span if l["y1"] >= y_top]
    below = [l for l in span if l["y1"] < y_top]

    # 每一栏各自聚类成"视觉行"，再按 上跨栏 → 左栏 → 右栏 → 下跨栏 输出
    ordered = (
        _cluster_lines(above)
        + _cluster_lines(left)
        + _cluster_lines(right)
        + _cluster_lines(below)
    )
    stat["rows"] = len(ordered)
    return "\n".join(m["text"] for m in ordered), stat


def pdf_pages(path: Path) -> tuple[list[tuple[int, str]], list[dict]]:
    """PDF → ([(页码, 文本)], [每页统计])。"""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams

    pages: list[tuple[int, str]] = []
    stats: list[dict] = []
    for i, layout in enumerate(extract_pages(str(path), laparams=LAParams()), start=1):
        text, stat = read_page(layout)
        stat["page"] = i
        pages.append((i, text))
        stats.append(stat)
    return pages, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", action="store_true", help="打印每页分栏统计")
    ns = ap.parse_args()

    src, dst = Path(ns.pdf), Path(ns.out)
    if not src.exists():
        print(f"[ERR] 找不到 {src}")
        return 2

    pages, stats = pdf_pages(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8") as f:
        for page, text in pages:
            f.write(f"\n===== 第 {page} 页 =====\n{text}\n")

    two = sum(1 for s in stats if s["cols"] == 2)
    print(f"抽出 {len(pages)} 页 / {sum(len(t) for _, t in pages)} 字 -> {dst}")
    print(f"识别为双栏的页: {two}/{len(pages)}")
    if ns.report:
        for s in stats:
            print(f"  第 {s['page']:>3} 页: {s['cols']} 栏, {s['lines']} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
