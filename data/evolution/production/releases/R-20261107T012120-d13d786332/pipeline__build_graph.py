#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""领域文档 → 知识图谱（规则抽取 + 引用回填）。

为什么是规则而不是直接让 LLM 抽：
  1. **可复现**：术语表与关系规则都是版本化文件，同一份文档永远抽出同一张图。
  2. **可溯源**：规则命中位置即 evidence 的字符区间，引用不是模型"编"出来的。
  3. **可审计**：每条边都能回答"你凭什么连这条边" —— 指向一条明文规则。
  LLM 的角色退到"提候选"（ontology/extraction_prompt.md），由本管线做确定性落库。

任何不确定抽取结果完整保留，标记 verification=pending 和启发式 confidence。
缺证据或端点的断言保留在候选集，不作为已核验事实或可执行诊疗规则。

用法：
    python pipeline/build_graph.py
    python pipeline/build_graph.py --doc 文件1.txt 文件2.txt --out data/processed/graph.json

默认构建三份 raw 重排全文；数值候选、引用版本疑点及覆盖范围见同名 .report.json。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from .document_blocks import load_blocks, compact, source_span
    from .management_extractor import describe_document, extract_management, identifier
    from .conflict_review import review_thresholds
    from .clinical_extractor import extract_clinical
    from .decision_extractor import extract_decisions
    from .verification import annotate, pending, retain_edges, preserve_previous_graph
except ImportError:
    from document_blocks import load_blocks, compact, source_span
    from management_extractor import describe_document, extract_management, identifier
    from conflict_review import review_thresholds
    from clinical_extractor import extract_clinical
    from decision_extractor import extract_decisions
    from verification import annotate, pending, retain_edges, preserve_previous_graph

# Windows 控制台默认 GBK，中文统计输出会炸
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY_DIR = ROOT / "ontology"

# 全角 → 半角，否则阈值正则要写两套
_FULLWIDTH = str.maketrans({
    "≥": ">=", "≤": "<=", "＞": ">", "＜": "<",
    "～": "~", "﹥": ">", "﹤": "<", "％": "%",
})


# --------------------------------------------------------------------------
# 1. 文档切块
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 2. 实体抽取（最长优先、不重叠）
# --------------------------------------------------------------------------

def load_lexicon() -> dict:
    return json.loads((ONTOLOGY_DIR / "lexicon.json").read_text(encoding="utf-8"))


def _surface_index(lexicon: dict) -> list[tuple[str, str, str]]:
    """(匹配串, 规范名, 类型)，按长度降序 —— 保证「高血压前期」不会被切成「高血压」+「前期」。"""
    out: list[tuple[str, str, str]] = []
    for t in lexicon["terms"]:
        for surface in [t["term"], *t.get("aliases", [])]:
            out.append((surface, t["term"], t["type"]))
    out.sort(key=lambda x: -len(x[0]))
    return out


def extract_entities(text: str, surfaces: list[tuple[str, str, str]]) -> list[dict]:
    taken = [False] * len(text)
    hits: list[dict] = []
    for surface, canon, typ in surfaces:
        start = 0
        while True:
            i = text.find(surface, start)
            if i < 0:
                break
            j = i + len(surface)
            if not any(taken[i:j]):
                for k in range(i, j):
                    taken[k] = True
                hits.append({"name": canon, "type": typ, "surface": surface, "pos": i})
            start = i + 1
    hits.sort(key=lambda h: h["pos"])
    # 保留所有提及位置，组装时合并实体身份并追加全部证据。
    return hits


# --------------------------------------------------------------------------
# 3. 数值约束抽取
# --------------------------------------------------------------------------

_DELIMS = "\n。；;，,：:•◦·、"
_RIGHT_STOP = "。；;\n•◦"

THRESHOLD_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("sbp_cmp",   re.compile(r"收缩压(?:[（(]?SBP[）)]?)?\s*(>=|<=|>|<)\s*(\d+(?:\.\d+)?)\s*mmHg")),
    ("dbp_cmp",   re.compile(r"舒张压(?:[（(]?DBP[）)]?)?\s*(>=|<=|>|<)\s*(\d+(?:\.\d+)?)\s*mmHg")),
    ("sbp_range", re.compile(r"收缩压\s*(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)\s*mmHg")),
    ("dbp_range", re.compile(r"舒张压\s*(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)\s*mmHg")),
    ("pair_range", re.compile(r"(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)\s*mmHg")),
    ("pair_cmp",  re.compile(r"(>=|<=|>|<)\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*mmHg")),
    ("salt",      re.compile(r"食盐不超过\s*(\d+(?:\.\d+)?)\s*克")),
    ("bmi",       re.compile(r"BMI\s*维持\s*(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)")),
    ("waist",     re.compile(r"(男|女)性腰围\s*(>=|<=|>|<)\s*(\d+(?:\.\d+)?)\s*cm")),
    ("exercise",  re.compile(r"每周累计\s*(\d+(?:\.\d+)?)\s*分钟")),
]

# 上下文标签：决定"同一个指标在不同测量方式下有不同阈值"能否被正确区分
_CONTEXT_RULES = [
    ("80岁及以上（耐受后）", ("耐受后再降至",)),
    ("家庭自测血压", ("家庭自测", "家庭动态")),
    ("24小时动态血压", ("24小时动态", "动态血压")),
    ("诊室血压", ("诊室",)),
    ("80岁及以上", ("80岁及以上", "高龄老人")),
    ("妊娠期", ("妊娠",)),
    ("合并糖尿病", ("合并糖尿病",)),
    ("非高危人群", ("非高危",)),
]

_CONTEXT_SCAN = 40  # 向前回溯多少字符来判定上下文


def _context_before(text: str, pos: int) -> str:
    window = text[max(0, pos - _CONTEXT_SCAN):pos]
    best, best_at = "", -1
    for label, keys in _CONTEXT_RULES:
        for k in keys:
            at = window.rfind(k)
            if at > best_at:
                best, best_at = label, at
    return best


def _sentence_around(text: str, start: int, end: int, limit: int = 220) -> str:
    left = start
    while left > 0 and text[left - 1] not in _DELIMS:
        left -= 1
    right = end
    while right < len(text) and text[right] not in _RIGHT_STOP:
        right += 1
    return text[left:min(right + 1, left + limit)].strip()


def _subject_for_section(section: str, topic: dict) -> tuple[str, str]:
    """返回 (subject, indicator 默认值)。subject 是"哪条规则"，indicator 是"看哪个指标"。"""
    disease = topic.get("disease", "")
    relation = topic.get("relation", "")
    if relation == "diagnosedBy":
        return f"{disease}诊断标准", ""
    if relation == "hasTarget":
        return f"{disease}控制目标", ""
    return disease or "通用", ""


def extract_thresholds(blocks: list[dict], topic_map: dict, doc_name: str) -> list[dict]:
    out: list[dict] = []
    for b in blocks:
        # 按字符建立归一化索引，>= 等展开后仍能精确回到原文。
        chars, positions = [], []
        for at, char in enumerate(b["raw"]):
            if char.isspace():
                continue
            replacement = char.translate(_FULLWIDTH)
            chars.append(replacement)
            positions.extend([at] * len(replacement))
        norm = "".join(chars)
        if b.get("legacy"):
            topic = topic_map.get(b["section"], {})
        elif "诊断标准" in b["title"]:
            topic = {"disease": "高血压", "relation": "diagnosedBy"}
        elif "降压目标" in b["title"]:
            topic = {"disease": "高血压", "relation": "hasTarget"}
        else:
            # 用途未知的数值也保留为候选，不能因标题不认识而丢掉。
            topic = {}
        base_subject, _ = _subject_for_section(b["section"], topic)
        for kind, pat in THRESHOLD_PATTERNS:
            for m in pat.finditer(norm):
                ctx = _context_before(norm, m.start())
                g = m.groups()
                items: list[tuple[str, str, float, str]] = []  # indicator, op, value, unit

                if kind == "sbp_cmp":
                    items.append(("收缩压", g[0], float(g[1]), "mmHg"))
                elif kind == "dbp_cmp":
                    items.append(("舒张压", g[0], float(g[1]), "mmHg"))
                elif kind == "sbp_range":
                    items.append(("收缩压", "range", float(g[0]), f"~{g[1]} mmHg"))
                elif kind == "dbp_range":
                    items.append(("舒张压", "range", float(g[0]), f"~{g[1]} mmHg"))
                elif kind == "pair_range":
                    items.append(("收缩压", "range", float(g[0]), f"~{g[1]} mmHg"))
                    items.append(("舒张压", "range", float(g[2]), f"~{g[3]} mmHg"))
                elif kind == "pair_cmp":
                    items.append(("收缩压", g[0], float(g[1]), "mmHg"))
                    items.append(("舒张压", g[0], float(g[2]), "mmHg"))
                elif kind == "salt":
                    items.append(("食盐摄入量", "<=", float(g[0]), "克/日"))
                elif kind == "bmi":
                    items.append(("体质指数", "range", float(g[0]), f"~{g[1]}"))
                elif kind == "waist":
                    items.append(("腰围", g[1], float(g[2]), "cm"))
                elif kind == "exercise":
                    items.append(("运动时长", ">=", float(g[0]), "分钟/周"))

                if kind in {"sbp_range", "dbp_range", "pair_range", "pair_cmp", "sbp_cmp", "dbp_cmp"}:
                    subject = base_subject
                else:
                    subject = items[0][0]

                for indicator, op, value, unit in items:
                    out.append({
                        "id": identifier("TH-", _tid(subject, indicator, op, value, ctx),
                                         doc_name, b["id"], m.start(), unit),
                        "subject": subject,
                        "indicator": indicator,
                        "operator": op,
                        "value": value,
                        "unit": unit,
                        "context": ctx,
                        "basis": f"{b['chapter']} / {b['section']} {b['title']}".strip(" /"),
                        "file": doc_name,
                        "section": b["section"],
                        "page": b.get("page"),
                        "block_id": b["id"],
                        "start": positions[m.start()], "end": positions[m.end() - 1] + 1,
                        "evidence": b["raw"][positions[m.start()]:positions[m.end() - 1] + 1],
                        "review_status": "scope_unverified",
                        "verification": "pending", "confidence": 0.45,
                        "confidence_basis": "rule_heuristic_not_calibrated",
                    })
    # 去重（同一块同一约束可能被两个模式同时命中）
    dedup: dict[str, dict] = {}
    for t in out:
        dedup.setdefault(t["id"], t)
    return list(dedup.values())


def _tid(subject: str, indicator: str, op: str, value: float, ctx: str) -> str:
    raw = f"{subject}|{indicator}|{op}|{value}|{ctx}"
    return "TH-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


# --------------------------------------------------------------------------
# 4. 关系抽取（规则驱动）
# --------------------------------------------------------------------------

def load_rules() -> dict:
    return json.loads((ONTOLOGY_DIR / "relation_rules.json").read_text(encoding="utf-8"))


def extract_relations(blocks: list[dict], rules: dict, node_names: set[str],
                      doc_name: str) -> tuple[list[dict], list[dict]]:
    """兼容旧摘要，部分命中/缺锚点/缺端点的规则提议完整保留。"""
    edges, candidates = [], []
    for block in blocks:
        norm = block["raw"].translate(_FULLWIDTH)
        text, _ = compact(block["raw"])
        citation = source_span(block, 0, len(text))
        for rule in rules["rules"]:
            if rule["section"] != block["section"]:
                continue
            requirements = rule.get("require_all", [])
            present = [term for term in requirements if term in norm]
            if requirements and not present:
                continue
            missing = [term for term in requirements if term not in norm]
            head, tail = rule["head"], rule["tail"]
            hint = rule.get("evidence_from") or next(iter(requirements), "")
            proposal = {"id": identifier("E-", rule["id"], doc_name, block["id"]),
                        "headId": "N-" + head, "relation": rule["relation"], "tailId": "N-" + tail,
                        "condition": rule.get("condition", ""), "rule": rule["id"],
                        "proposed_rule": rule, **citation}
            reasons = []
            if missing:
                reasons.append("rule_partially_matched")
                proposal["missing_terms"] = missing
            if hint not in norm:
                reasons.append("evidence_anchor_missing")
            if head not in node_names or tail not in node_names:
                reasons.append("endpoint_not_extracted")
            if reasons:
                candidates.append(pending(proposal, 0.25, *reasons))
            else:
                edges.append(pending(proposal, 0.8, "legacy_summary_rule_requires_review"))
    return edges, candidates


def _eid(head: str, relation: str, tail: str, condition: str) -> str:
    raw = f"{head}|{relation}|{tail}|{condition}"
    return "E-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


# --------------------------------------------------------------------------
# 5. 组装 + 校验
# --------------------------------------------------------------------------

def build(doc_path: Path | list[Path]) -> dict:
    """同一词项合并节点；每一份文件/章节的断言保留独立证据。"""
    paths = [doc_path] if isinstance(doc_path, Path) else list(doc_path)
    paths = list(dict.fromkeys(p.resolve() for p in paths))
    if not paths:
        raise ValueError("至少需要一份文档")
    if len({p.name for p in paths}) != len(paths):
        raise ValueError("不同目录下同名文档会造成出处歧义，请先重命名")
    lexicon, rules = load_lexicon(), load_rules()
    management_rules = json.loads((ONTOLOGY_DIR / "management_rules.json").read_text(encoding="utf-8"))
    clinical_rules = json.loads((ONTOLOGY_DIR / "clinical_relation_rules.json").read_text(encoding="utf-8"))
    decision_rules = json.loads((ONTOLOGY_DIR / "decision_rules.json").read_text(encoding="utf-8"))
    surfaces = _surface_index(lexicon)
    loaded = [(p, load_blocks(p)) for p in paths]
    documents = [describe_document(p.name, blocks) for p, blocks in loaded]
    for document in documents:
        pending(document, 0.55 if document["warnings"] else 0.9, "document_metadata_requires_review")
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    thresholds: dict[str, dict] = {}
    threshold_candidates: dict[str, dict] = {}
    edge_candidates: list[dict] = []
    entity_candidates: list[dict] = []
    extraction_candidates: list[dict] = []
    decisions: list[dict] = []
    all_blocks: list[dict] = []

    def merge_node(n: dict) -> None:
        if n["id"] not in nodes:
            nodes[n["id"]] = n
            return
        existing = nodes[n["id"]]
        existing.setdefault("evidences", [])
        for citation in n.get("evidences", []):
            if citation not in existing["evidences"]:
                existing["evidences"].append(citation)
        existing["sections"] = sorted(set(existing.get("sections", []) + n.get("sections", [])))
        existing["attributes"].update(n.get("attributes", {}))
        if n.get("verification") == "pending":
            pending(existing, min(existing.get("confidence", 1.0), n["confidence"]),
                    *n.get("verification_reasons", []))

    for (path, blocks), document in zip(loaded, documents):
        all_blocks.extend(blocks)
        for block in blocks:
            text, _ = compact(block["raw"])
            entities = extract_entities(text, surfaces)
            accepted = {(e["name"], e["pos"], len(e["surface"])) for e in entities}
            for entity in entities:
                citation = source_span(block, entity["pos"], entity["pos"] + len(entity["surface"]))
                nid = f"N-{entity['name']}"
                aliases = next(t.get("aliases", []) for t in lexicon["terms"] if t["term"] == entity["name"])
                merge_node({"id": nid, "name": entity["name"], "type": entity["type"],
                            "aliases": aliases, "attributes": {}, **citation,
                            "sections": [block["section"]], "evidences": [citation]})
                eid = identifier("E-", nid, "evidencedBy", document["id"], block["id"], entity["pos"])
                edges[eid] = {"id": eid, "headId": nid, "relation": "evidencedBy",
                              "tailId": document["id"], "condition": "", "rule": "R-SOURCE-MEMBERSHIP", **citation}
            alternatives = {}
            for surface, name, typ in surfaces:
                for match in re.finditer(re.escape(surface), text):
                    if (name, match.start(), len(surface)) in accepted:
                        continue
                    ident = identifier("C-ENTITY-", name, typ, block["id"], match.start(), match.end())
                    alternatives[ident] = pending({"id": ident, "kind": "overlapping_entity_match",
                                                   "name": name, "type": typ, "surface": surface,
                                                   **source_span(block, match.start(), match.end())},
                                                  0.4, "overlaps_longer_entity")
            entity_candidates.extend(alternatives.values())
            for match in re.finditer(r"\d+(?:\.\d+)?(?:[/~～]\d+(?:\.\d+)?)*\s*(?:mmHg|mmol/L|mg/dl|mg|µmol/L|ml/|次/min)", text):
                extraction_candidates.append(pending({"id": identifier("C-NUM-", block["id"], match.start(), match.end()),
                                                       "kind": "numeric_mention", "reason": "数值用途、单位或上下文待核验",
                                                       **source_span(block, match.start(), match.end())}, 0.35, "numeric_scope_unverified"))

        # 旧摘要的 4.1 等节号与原始标准的 4.1 含义不同，不得跨格式套用。
        if document["profile"] == "legacy":
            legacy_edges, dropped = extract_relations(blocks, rules, {n["name"] for n in nodes.values()}, path.name)
            edge_candidates.extend(dropped)
            for edge in legacy_edges:
                edges[edge["id"]] = edge
        extra_nodes, extra_edges, extra_thresholds = extract_management(blocks, document, documents, lexicon, management_rules)
        for n in extra_nodes:
            merge_node(n)
        for edge in extra_edges:
            edges[edge["id"]] = edge
        clinical_nodes, clinical_edges, clinical_candidates = extract_clinical(blocks, document, clinical_rules)
        for n in clinical_nodes:
            merge_node(n)
        for edge in clinical_edges:
            edges[edge["id"]] = edge
        extraction_candidates.extend(clinical_candidates)
        extracted = extract_thresholds(blocks, rules.get("section_topic", {}), path.name)
        # 全文数值涉及表格列、人群、测量时段，未核验前只进入候选集。
        if document["profile"] != "legacy":
            threshold_candidates.update({t["id"]: t for t in extracted})
            extracted = []  # 记录已完整存入 threshold_candidates，并未删除。
        for threshold in extracted + extra_thresholds:
            thresholds[threshold["id"]] = threshold
        decision_thresholds, document_decisions = extract_decisions(blocks, document, decision_rules)
        decisions.extend(document_decisions)
        for threshold in decision_thresholds:
            # 新的可计算结构与原候选并存；不把“可执行”冒充“已核验”。
            threshold["derived_from"] = [t["id"] for t in [*threshold_candidates.values(), *extraction_candidates]
                                         if t.get("block_id") == threshold["block_id"]
                                         and t.get("start", 0) < threshold["end"]
                                         and t.get("end", 0) > threshold["start"]]
            thresholds[threshold["id"]] = threshold

    kept, incomplete = retain_edges(list(edges.values()), nodes)
    edge_candidates.extend(incomplete)
    for collection in (list(nodes.values()), list(thresholds.values()), list(threshold_candidates.values()),
                       edge_candidates, entity_candidates, extraction_candidates, decisions):
        for record in collection:
            annotate(record)
    return {
        "meta": {
            "domain": "高血压临床诊疗与基层慢病管理",
            "ontology_version": json.loads((ONTOLOGY_DIR / "ontology.json").read_text(encoding="utf-8"))["version"],
            "lexicon_version": lexicon["version"], "rules_version": clinical_rules["version"],
            "legacy_rules_version": rules["version"],
            "management_rules_version": management_rules["version"],
            "clinical_rules_version": clinical_rules["version"],
            "decision_rules_version": decision_rules["version"],
            "retention_policy": "uncertain_results_retained_pending",
            "confidence_definition": "0~1规则启发式抽取评分；未经概率校准，不是医学正确率，不能替代人工核验。",
            "built_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "source_docs": [p.name for p in paths], "documents": documents,
            "builder": "pipeline/build_graph.py", "page_numbering": "PDF physical page, null if unknown",
            "limitations": ["表格勾选关系未恢复，不推断表格列对应关系。",
                            "标准第 4、6 物理页存在文本错序，章节标记需核读，原文和页码仍保留。",
                            "全文数字候选全部保留；诊室血压边界经双证据结构化后仅供数学比较，仍待临床核验，不自动确诊。",
                            "三份全文药物关系使用分源新规则；所有自动抽取关系待人工核验。",
                            "未解析药物语句、数字及重叠实体保留为待核验候选，缺端点/证据断言完整保留。",
                            "数值不同仅为待核对差异，不能自动认定为医学冲突。"]
        },
        "nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["name"])),
        "edges": sorted(kept, key=lambda e: (e["relation"], e["headId"], e["id"])),
        "thresholds": sorted(thresholds.values(), key=lambda t: (t["subject"], t["indicator"], t["value"], t["id"])),
        "threshold_candidates": list(threshold_candidates.values()),
        "decision_rules": decisions,
        "edge_candidates": edge_candidates, "entity_candidates": entity_candidates,
        "extraction_candidates": extraction_candidates,
        "blocks": all_blocks, "discarded": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", nargs="+", action="extend", help="可传多个文件，也可重复 --doc；默认三份 raw/*_重排.txt")
    ap.add_argument("--out", default="data/processed/graph.json")
    ap.add_argument("--report", help="构建报告路径，默认与图谱同名的 .report.json")
    args = ap.parse_args()

    names = args.doc or ["data/raw/WS-T872-2025_重排.txt",
                         "data/raw/国家基层高血压防治管理指南2025版_重排.txt",
                         "data/raw/中国高血压临床实践指南2025版_重排.txt"]
    doc_paths = [(ROOT / name) if not Path(name).is_absolute() else Path(name) for name in names]
    out_path = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    report_path = Path(args.report) if args.report else out_path.with_suffix(".report.json")
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    if report_path.resolve() == out_path.resolve():
        raise ValueError("报告与图谱不能使用同一路径")
    if out_path.resolve() in {p.resolve() for p in doc_paths} or report_path.resolve() in {p.resolve() for p in doc_paths}:
        raise ValueError("图谱或报告不能覆盖输入文档")
    for doc_path in doc_paths:
        if not doc_path.is_file():
            print(f"[ERR] 找不到文档: {doc_path}")
            return 2

    graph = build(doc_paths)
    by_type: dict[str, int] = {}
    for n in graph["nodes"]:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    by_rel: dict[str, int] = {}
    for e in graph["edges"]:
        by_rel[e["relation"]] = by_rel.get(e["relation"], 0) + 1

    print("=" * 62)
    print(f"文档   : {len(doc_paths)} 份")
    print(f"节点   : {len(graph['nodes'])}   " + " ".join(f"{k}={v}" for k, v in sorted(by_type.items())))
    print(f"边     : {len(graph['edges'])}   " + " ".join(f"{k}={v}" for k, v in sorted(by_rel.items())))
    print(f"阈值   : {len(graph['thresholds'])}")
    print(f"数值候选（待核验）: {len(graph['threshold_candidates'])}")
    print(f"待核验候选: 关系 {len(graph['edge_candidates'])} / 实体 {len(graph['entity_candidates'])} / 片段 {len(graph['extraction_candidates'])}")
    print("丢弃   : 0（不确定抽取完整保留）")
    print("=" * 62)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    preserve_previous_graph(graph, out_path)
    out_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写出 -> {out_path}")
    report = {
        "documents": graph["meta"]["documents"],
        "counts": {"documents": len(graph["meta"]["source_docs"]), "blocks": len(graph["blocks"]),
                   "nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
                   "thresholds": len(graph["thresholds"]), "discarded": len(graph["discarded"])},
        "decision_rules_count": len(graph["decision_rules"]),
        "threshold_candidates_count": len(graph["threshold_candidates"]),
        "pending_counts": {key: sum(r.get("verification") == "pending" for r in graph[key])
                           for key in ("nodes", "edges", "thresholds", "threshold_candidates", "edge_candidates", "entity_candidates", "extraction_candidates", "decision_rules")},
        "clinical_relations_by_source": {document["file"]: sum(e.get("extraction_basis") == "全文规则" and e["file"] == document["file"]
                                                               for e in graph["edges"]) for document in graph["meta"]["documents"]},
        "history_snapshots": graph["meta"].get("history_snapshots", []),
        "relations": by_rel,
        "references": [e for e in graph["edges"] if e["relation"] == "references"],
        "conflicts": review_thresholds(graph["thresholds"]),
        "limitations": graph["meta"]["limitations"],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"构建报告 -> {report_path}")
    print("数值差异: 已确认冲突 0；待核对差异 " + str(len(report["conflicts"]["candidates"]))
          + "；药物作用域对照请调用MCP detect_conflicts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
