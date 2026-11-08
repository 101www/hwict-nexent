"""只报告待核对差异；来源、人群、目的和测量方式未核对时不宣称真冲突。"""
from __future__ import annotations

try:
    from .verification import pending
except ImportError:
    from verification import pending


def review_thresholds(thresholds: list[dict]) -> dict:
    groups: dict[tuple, list[dict]] = {}
    for item in thresholds:
        groups.setdefault((item["subject"], item["indicator"], item["unit"], item.get("context", "")), []).append(item)
    candidates = []
    within_document = []
    for (subject, indicator, unit, context), items in groups.items():
        signatures = {(t["operator"], t["value"]) for t in items}
        if len(signatures) <= 1:
            continue
        entry = pending({"subject": subject, "indicator": indicator, "unit": unit, "context": context,
                 "items": items, "status": "needs_review",
                 "reason": "需核对适用人群、临床目的、测量方式、版本及条件；数值差异不等于逻辑冲突。"},
                        0.4, "conflict_not_adjudicated")
        (candidates if len({t["file"] for t in items}) > 1 else within_document).append(entry)
    return {"hard": [], "candidates": candidates, "within_document": within_document,
            "note": "hard 保留兼容字段；未经人工裁决，本管线不自动生成已确认冲突。"}
