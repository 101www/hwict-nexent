#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 graph.json 上做多跳查询 —— 用于离线验证图谱，不依赖 Nexent 全栈。

本脚本验证离线图谱。Spring AI Java MCP 已读取同一图谱；协议测试见 java-mcp/test_real_graph_mcp.py。

用法：
    python tools/query_graph.py demo
    python tools/query_graph.py find 糖尿病
    python tools/query_graph.py path 高血压 血管紧张素转换酶抑制剂 --hops 2
    python tools/query_graph.py threshold 高血压
    python tools/query_graph.py conflicts
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.conflict_review import review_thresholds
GRAPH_PATH = ROOT / "data" / "processed" / "graph.json"

# 面向"从疾病问到用药"的关系集合
DRUG_RELATIONS = {"firstLineFor", "preferredFor", "recommendedFor", "excludedFromFirstLine",
                  "contraindicatedFor", "cautionFor", "combinedWith", "instanceOf"}

# 溯源标注边，不参与推理遍历（否则路径会走进 SourceDoc 死胡同）
SKIP_RELATIONS = {"evidencedBy", "containsSection", "references"}

class Graph:
    def __init__(self, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.meta = data["meta"]
        self.nodes = {n["id"]: n for n in data["nodes"]}
        self.thresholds = data["thresholds"]
        self.edges = data["edges"]
        self.candidates = [*data.get("edge_candidates", []), *data.get("entity_candidates", []),
                           *data.get("extraction_candidates", []), *data.get("threshold_candidates", [])]
        self.by_name = {n["name"]: n for n in data["nodes"]}
        self.out: dict[str, list[dict]] = {}
        self.inc: dict[str, list[dict]] = {}
        for e in self.edges:
            self.out.setdefault(e["headId"], []).append(e)
            self.inc.setdefault(e["tailId"], []).append(e)

    # ---- 基础检索 ----
    def find(self, keyword: str) -> list[dict]:
        kw = keyword.strip().lower()
        return [n for n in self.nodes.values()
                if kw in n["name"].lower() or any(kw in a.lower() for a in n.get("aliases", []))]

    def thresholds_of(self, disease: str) -> list[dict]:
        return [t for t in self.thresholds if t["subject"].startswith(disease)]

    # ---- 多跳：无向遍历，命中终点即返回路径 ----
    def paths(self, start: str, end: str, max_hops: int = 3, limit: int = 6,
              via: str | None = None) -> list[dict]:
        s, t = self.by_name.get(start), self.by_name.get(end)
        if not s or not t:
            return []
        found: list[dict] = []
        queue = deque([(s["id"], [], {s["id"]})])
        while queue:
            cur, trail, seen = queue.popleft()
            if len(trail) >= max_hops:
                continue
            for e in [*self.out.get(cur, []), *self.inc.get(cur, [])]:
                if e["relation"] in SKIP_RELATIONS:
                    continue
                forward = e["headId"] == cur
                nxt = e["tailId"] if forward else e["headId"]
                if nxt in seen:
                    continue
                step = {"edge": e, "forward": forward, "from": cur, "to": nxt}
                new_trail = trail + [step]
                if via and not any(self.nodes[x]["name"] == via
                                   for st in new_trail for x in (st["from"], st["to"])):
                    continue
                if nxt == t["id"]:
                    found.append({"steps": new_trail, "hops": len(new_trail), "verification": "pending",
                                  "confidence": min(step["edge"].get("confidence", 0.0) for step in new_trail),
                                  "sufficient": False, "kind": "evidence_path",
                                  "note": "仅表示证据图连通；适用条件、联合方案及临床决策尚未核验。"})
                    if len(found) >= limit:
                        return sorted(found, key=lambda p: p["hops"])
                    continue
                queue.append((nxt, new_trail, seen | {nxt}))
        return sorted(found, key=lambda p: p["hops"])

    def render_path(self, p: dict) -> str:
        lines = []
        for i, st in enumerate(p["steps"], 1):
            e = st["edge"]
            a = self.nodes[st["from"]]["name"]
            b = self.nodes[st["to"]]["name"]
            arrow = f"{a} --{e['relation']}--> {b}" if st["forward"] else f"{b} --{e['relation']}--> {a}"
            cond = f"  [{e['condition']}]" if e.get("condition") else ""
            lines.append(f"   {i}. {arrow}{cond}")
            lines.append(f"      核验: {e.get('verification', 'pending')} · confidence={e.get('confidence', 0.0)}")
            lines.append(f"      出处: {e['file']} · §{e['section']} · 「{e['evidence']}」")
        return "\n".join(lines)

    # ---- 冲突检测：区分"真冲突"和"测量方式差异导致的伪冲突" ----
    def conflicts(self) -> dict:
        return review_thresholds(self.thresholds)

    def pending_candidates(self, keyword: str = "") -> list[dict]:
        return [item for item in self.candidates
                if not keyword or keyword.lower() in json.dumps(item, ensure_ascii=False).lower()]

    def reference_status(self, keyword: str = "") -> list[dict]:
        """给下游返回证据充分性，不把已入库的另一版本当作引用原件。"""
        messages = {
            "missing": "被引用文件未入库；仅能说明引用关系，无法给出该文件的具体要求。",
            "version_mismatch": "已有同名候选文档，但与参考文献指向的版本不同；需核验版本后才能补全依据。",
            "version_unverified": "已有同名候选文档，但引用版本未确认；需先核验。",
            "resolved": "被引用文件及版本已匹配；仍需检索并核对具体条款后作答。",
        }
        return [{"reference": e, "target": self.nodes[e["tailId"]]["name"],
                 "message": messages[e["resolution"]]}
                for e in self.edges if e["relation"] == "references"
                and (not keyword or keyword in e["file"] or keyword in self.nodes[e["tailId"]]["name"])]


def _cite(t: dict) -> str:
    ctx = f"[{t['context']}]" if t.get("context") else ""
    return f"[{t.get('verification', 'pending')}, confidence={t.get('confidence', 0.0)}] {t['indicator']} {t['operator']} {t['value']} {t['unit']}{ctx}  ← {t['file']} · §{t['section']} · 「{t['evidence']}」"


def cmd_demo(g: Graph) -> None:
    print("=" * 78)
    print(f"图谱版本 {g.meta['ontology_version']}  节点 {len(g.nodes)}  边 {len(g.edges)}  阈值 {len(g.thresholds)}")
    print("=" * 78)

    print("\n【Q1】高血压的诊断标准是什么？")
    hits = g.thresholds_of("高血压诊断标准")
    if hits:
        print("  命中抽取的数值约束，以下状态需与原文一并核验：")
        for t in hits:
            print("    · " + _cite(t))
    else:
        print("  当前图谱没有已核验的结构化阈值；需检索原文或说明证据不足。")

    print("\n【Q2】高血压前期的血压范围是多少？")
    hits = g.thresholds_of("高血压前期诊断标准")
    if hits:
        print("  ✔ 命中图谱：")
        for t in hits:
            print("    · " + _cite(t))
    else:
        print("  当前图谱没有已核验的结构化阈值；需检索原文或说明证据不足。")

    print("\n【Q3】合并糖尿病的高血压患者首选哪类降压药？（需要跨小节多跳）")
    dm = g.by_name.get("糖尿病")
    if not dm:
        print("  ✘ 图中无糖尿病节点")
    else:
        print("  第 0 跳（合并症确认）：")
        for e in g.inc.get(dm["id"], []):
            if e["relation"] == "complicates":
                print(f"    · {g.nodes[e['headId']]['name']} --complicates--> 糖尿病   出处: §{e['section']} 「{e['evidence']}」")
        print("  第 1 跳（糖尿病 → 用药）：")
        rows = []
        for e in g.inc.get(dm["id"], []):
            if e["relation"] in DRUG_RELATIONS:
                rows.append(e)
        # 排序：preferredFor / firstLineFor 优先
        rank = {"preferredFor": 0, "firstLineFor": 1, "recommendedFor": 2}
        rows.sort(key=lambda e: rank.get(e["relation"], 9))
        for e in rows:
            cls = g.nodes[e["headId"]]
            mark = "★首选" if e["relation"] == "preferredFor" else " "
            print(f"    {mark} {cls['name']} --{e['relation']}--> 糖尿病   出处: §{e['section']} 「{e['evidence']}」")
        # 反向多跳：高血压 → 糖尿病 ← 药物（必须经过糖尿病节点，证明是 2 跳而非查表）
        print("  跨小节多跳（限定必须经过「糖尿病」节点）：")
        found = g.paths("高血压", "血管紧张素转换酶抑制剂", max_hops=3, limit=4, via="糖尿病")
        if found:
            for p in found:
                print(f"   ── {p['hops']} 跳 ──")
                print(g.render_path(p))
        else:
            print("    （未找到）")

    print("\n【Q4】阿司匹林对房颤患者的推荐剂量是多少？（考察拒答）")
    hits = g.find("阿司匹林")
    if not hits:
        print("  当前受控词表未收录「阿司匹林」；不能据此判断原文没有相关内容，需补充检索和核验。")
    else:
        print(f"  ✘ 意外命中：{[n['name'] for n in hits]}")

    print("\n【附加】阈值冲突检测")
    c = g.conflicts()
    print(f"  已确认冲突（需人工裁决）: {len(c['hard'])}")
    for h in c["hard"]:
        print(f"    ! {h['subject']} / {h['indicator']} / {h['context']}")
    print(f"  跨文档待核对差异: {len(c['candidates'])}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["demo", "find", "path", "threshold", "conflicts", "references", "relations", "candidates"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--hops", type=int, default=3)
    ap.add_argument("--graph", type=Path, default=GRAPH_PATH)
    ns = ap.parse_args()

    g = Graph(ns.graph)
    if (ns.cmd in {"find", "threshold"} and not ns.args) or (ns.cmd == "path" and len(ns.args) < 2):
        ap.error("find/threshold 需要一个关键词；path 需要起点和终点")

    if ns.cmd == "demo":
        cmd_demo(g)
    elif ns.cmd == "find":
        for n in g.find(ns.args[0]):
            print(f"{n['type']:12} {n['name']:24} 别名={n.get('aliases')}  出处=§{n['section']}")
    elif ns.cmd == "path":
        ps = g.paths(ns.args[0], ns.args[1], max_hops=ns.hops)
        print(f"命中 {len(ps)} 条路径（≤{ns.hops} 跳）")
        for p in ps:
            print(f"\n-- {p['hops']} 跳 --")
            print(g.render_path(p))
    elif ns.cmd == "threshold":
        for t in g.thresholds_of(ns.args[0]):
            print(_cite(t))
    elif ns.cmd == "conflicts":
        c = g.conflicts()
        print(json.dumps({k: len(v) for k, v in c.items() if isinstance(v, list)}, ensure_ascii=False))
    elif ns.cmd == "references":
        print(json.dumps(g.reference_status(ns.args[0] if ns.args else ""), ensure_ascii=False, indent=2))
    elif ns.cmd == "candidates":
        print(json.dumps(g.pending_candidates(ns.args[0] if ns.args else ""), ensure_ascii=False, indent=2))
    elif ns.cmd == "relations":
        keyword = ns.args[0] if ns.args else ""
        for e in g.edges:
            if e["relation"] in SKIP_RELATIONS:
                continue
            head, tail = g.nodes[e["headId"]]["name"], g.nodes[e["tailId"]]["name"]
            if keyword and not any(keyword in value for value in (head, tail, e["relation"])):
                continue
            print(f"{head} --{e['relation']}--> {tail}")
            print(f"  verification={e.get('verification', 'pending')} · confidence={e.get('confidence', 0.0)}")
            print(f"  {e['file']} · PDF第{e['page']}页 · §{e['section']} · {e.get('modality', '')}")
            print(f"  {e['evidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
