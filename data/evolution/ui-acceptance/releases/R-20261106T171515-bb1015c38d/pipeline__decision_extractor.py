"""只将同节明确的边界和测量协议结构化；保留所有旧候选，绝不自动完成人工核验。"""
from __future__ import annotations

import re

try:
    from .document_blocks import compact, source_span
    from .management_extractor import identifier
    from .verification import pending
except ImportError:
    from document_blocks import compact, source_span
    from management_extractor import identifier
    from verification import pending


def extract_decisions(blocks: list[dict], document: dict, config: dict) -> tuple[list[dict], list[dict]]:
    thresholds, decisions = [], []
    for rule in config["rules"]:
        if document["profile"] != rule["profile"]:
            continue
        for block in blocks:
            if block["section"] != rule["section"]:
                continue
            text, _ = compact(block["raw"])
            protocol = re.search(rule["protocol_pattern"], text)
            boundary = re.search(rule["boundary_pattern"], text)
            # 两处数值一致且明确写有“和(或)”才允许数学执行。单独一段140/90仍只是候选。
            if not protocol or not boundary or any(protocol[k] != boundary[k] for k in ("sbp", "dbp")):
                continue
            citation = source_span(block, boundary.start(), boundary.end())
            supporting = source_span(block, protocol.start(), protocol.end())
            rid = identifier("DR-", rule["id"], block["id"])
            ids = []
            for key, indicator in (("sbp", "收缩压"), ("dbp", "舒张压")):
                tid = identifier("T-", rid, key)
                ids.append(tid)
                thresholds.append(pending({"id": tid, "subject": "高血压诊室血压诊断边界",
                                           "indicator": indicator, "value": float(boundary[key]),
                                           "operator": rule["operator"], "unit": rule["unit"],
                                           "context": "诊室血压；非单次确诊", "comparison_scope": rule["scope"],
                                           "decision_rule_id": rid, "rule": rule["id"],
                                           "role": key, "logic": rule["logic"],
                                           "execution_status": "mathematical_only_pending_clinical_review",
                                           **citation, "supporting_evidence": [supporting]},
                                          0.9, "clinical_review_required"))
            decisions.append(pending({"id": rid, "kind": "blood_pressure_boundary",
                                      "rule": rule["id"], "measurement_method": rule["method"],
                                      "logic": rule["logic"], "threshold_ids": ids, "scope": rule["scope"],
                                      "requirements": {"minimum_visits": int(protocol["count"]),
                                                       "maximum_days": int(protocol["weeks"]) * 7,
                                                       "non_same_day": True, "standardized": True,
                                                       "every_visit_reaches_boundary": True},
                                      **citation, "supporting_evidence": [supporting],
                                      "sufficient": False}, 0.9, "clinical_review_required"))
    return thresholds, decisions
