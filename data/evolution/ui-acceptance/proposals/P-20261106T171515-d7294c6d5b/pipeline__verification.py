"""抽取置信度是规则启发式评分，不代表医学正确率或人工审核。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def pending(record: dict, confidence: float = 0.5, *reasons: str) -> dict:
    record["verification"] = "pending"
    record["confidence"] = round(max(0.0, min(1.0, confidence)), 3)
    record["confidence_basis"] = "rule_heuristic_not_calibrated"
    existing = list(record.get("verification_reasons", []))
    record["verification_reasons"] = existing
    for reason in reasons:
        if reason and reason not in existing:
            existing.append(reason)
    return record


def annotate(record: dict) -> dict:
    """所有自动抽取默认待核验；布局、缺证据、缺端点等进一步降低评分。"""
    if record.get("verification") == "pending":
        score = record.get("confidence", 0.5)
    else:
        score = 0.95 if record.get("relation") in {"containsSection", "evidencedBy"} else 0.85
    reasons = []
    if record.get("section_status") == "needs_layout_review":
        score = min(score, 0.55)
        reasons.append("layout_or_section_unverified")
    if record.get("review_status") in {"scope_unverified", "needs_review"}:
        score = min(score, 0.55)
        reasons.append(record["review_status"])
    if record.get("resolution") in {"missing", "version_mismatch", "version_unverified"}:
        score = min(score, 0.55)
        reasons.append(record["resolution"])
    if not record.get("evidence"):
        score = min(score, 0.1)
        reasons.append("evidence_missing")
    return pending(record, score, *reasons)


def retain_edges(edges: list[dict], nodes: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """结构不完整的原始断言完整保留在候选集中，避免破坏可遍历图的端点约束。"""
    kept, candidates = [], []
    for edge in edges:
        errors = []
        if edge.get("headId") not in nodes:
            errors.append("head_node_missing")
        if edge.get("tailId") not in nodes:
            errors.append("tail_node_missing")
        if not edge.get("evidence", "").strip():
            errors.append("evidence_missing")
        if errors:
            candidate = dict(edge)
            candidate["validation_errors"] = errors
            candidates.append(pending(candidate, 0.1, *errors))
        else:
            kept.append(annotate(edge))
    return kept, candidates


def preserve_previous_graph(graph: dict, path: Path) -> None:
    """重建改变内容时先保存完整旧图；历史文件包含旧原文块，旧偏移仍可核读。"""
    if not path.is_file():
        return
    payload = path.read_bytes()
    try:
        previous = json.loads(payload)
    except (ValueError, UnicodeError):
        previous = None
    history = previous.get("meta", {}).get("history_snapshots", []) if isinstance(previous, dict) else []

    def semantic(value: dict) -> str:
        value = {**value, "meta": dict(value.get("meta", {}))}
        for key in ("built_at", "history_snapshots"):
            value["meta"].pop(key, None)
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    if isinstance(previous, dict) and semantic(previous) == semantic(graph):
        graph["meta"]["history_snapshots"] = list(history)
        return
    digest = hashlib.sha256(payload).hexdigest()
    folder = path.parent / (path.stem + ".history")
    folder.mkdir(parents=True, exist_ok=True)
    snapshot = folder / (digest + ".json")
    if not snapshot.exists():
        snapshot.write_bytes(payload)
    entry = {"path": str(snapshot.resolve()), "sha256": digest,
             "reason": "保留重建前的完整抽取结果、待核验候选及原文块", "verification": "pending",
             "confidence": 1.0, "confidence_basis": "exact_file_snapshot_sha256"}
    graph["meta"]["history_snapshots"] = list(history) + ([entry] if not any(item["sha256"] == digest for item in history) else [])
