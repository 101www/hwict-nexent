"""管理条款的保守抽取：保留义务强度、适用主体和完整条件，引用版本不自动升级。"""
from __future__ import annotations

import hashlib
import re

try:
    from .document_blocks import compact, source_span
except ImportError:
    from document_blocks import compact, source_span


def identifier(prefix: str, *parts: object) -> str:
    return prefix + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:14]


def describe_document(name: str, blocks: list[dict]) -> dict:
    text, _ = compact("\n".join(b["raw"] for b in blocks))
    intro = text[:8000]
    if "WS/T872" in intro:
        title, year, profile = "基层医疗卫生机构高血压防治管理标准", "2025", "standard"
    elif "国家基层高血压防治管理指南" in intro:
        title, profile = "国家基层高血压防治管理指南", "primary"
        edition = re.search(r"国家基层高血压防治管理指南[（(]?(20\d{2})", intro)
        issue = re.search(r"ChineseCirculationJournal,(20\d{2})", intro)
        year = edition[1] if edition else issue[1] if issue else ""
    elif "中国高血压临床实践指南" in intro:
        title, profile = "中国高血压临床实践指南", "clinical"
        issue = re.search(r"中华心血管病杂志(20\d{2})年", intro)
        year = issue[1] if issue else ""
    else:
        title, year, profile = name, "", "other"
    if any(b["legacy"] for b in blocks):
        profile = "legacy"
    warnings = []
    filename_year = re.search(r"20\d{2}", name)
    if filename_year and year and filename_year[0] != year:
        warnings.append(f"文件名年份 {filename_year[0]} 与正文刊期 {year} 不同；正文年份仍需人工核验。")
    # 标准参考文献给出了所引用指南的年份，不能把 2021 引用悄悄绑定到 2025。
    referenced = re.search(r"国家基层高血压防治管理指南\[J\].{0,60}?(20\d{2})", text)
    reference_year_evidence = None
    if referenced:
        for block in blocks:
            value, _ = compact(block["raw"])
            found = re.search(r"国家基层高血压防治管理指南\[J\].{0,60}?(20\d{2})", value)
            if found:
                reference_year_evidence = source_span(block, found.start(), found.end())
                break
    return {"id": identifier("N-DOC-", name), "file": name, "title": title,
            "year": year, "profile": profile, "warnings": warnings,
            "reference_year_evidence": reference_year_evidence,
            "referenced_primary_year": referenced[1] if referenced else ""}


def extract_management(blocks: list[dict], document: dict, documents: list[dict],
                       lexicon: dict, rules: dict) -> tuple[list[dict], list[dict], list[dict]]:
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    thresholds: list[dict] = []

    def node(nid: str, name: str, typ: str, citation: dict, **attributes: object) -> str:
        if nid not in nodes:
            nodes[nid] = {"id": nid, "name": name, "type": typ, "aliases": [],
                          "attributes": attributes, **citation, "evidences": [citation],
                          "sections": [citation["section"]]}
        elif citation not in nodes[nid]["evidences"]:
            nodes[nid]["evidences"].append(citation)
        return nid

    def term(name: str, typ: str, citation: dict) -> str:
        return node(f"N-{name}", name, typ, citation)

    def edge(head: str, relation: str, tail: str, citation: dict, rule: str,
             condition: str = "", **extra: object) -> None:
        eid = identifier("E-", head, relation, tail, citation["block_id"], citation["start"], condition)
        edges[eid] = {"id": eid, "headId": head, "relation": relation, "tailId": tail,
                      "condition": condition, "rule": rule, **citation, **extra}

    equipment = [t for t in lexicon["terms"] if t["type"] == "Equipment"]
    for block in blocks:
        text, _ = compact(block["raw"])
        if not text:
            continue
        full = source_span(block, 0, len(text))
        doc_id = node(document["id"], document["title"] + (f"（{document['year']}）" if document["year"] else ""),
                      "SourceDoc", full, loaded=True, year=document["year"], profile=document["profile"])
        section_id = node("N-" + block["id"], f"{document['file']} §{block['section']} p{block['page']}",
                          "Section", full, title=block["title"])
        edge(doc_id, "containsSection", section_id, full, "R-DOCUMENT-SECTION")
        if document["profile"] not in {"standard", "primary"}:
            continue

        title_context = " / ".join(block.get("heading_path", []) + [block["title"]])
        equipment_subject = "社区卫生服务中心和乡镇卫生院" if block["section"] == "4.1.2" and document["profile"] == "standard" else "基层医疗卫生机构"
        # 设备段只取有明确配备谓词的完整句子；宜、建议和应分别记录。
        for match in re.finditer(r"[^。！？]+[。！？]?", text):
            sentence = match[0]
            citation = source_span(block, match.start(), match.end())
            requirement = re.search(r"(均应|还应|应|宜|建议)配备", sentence)
            if requirement and any(word in title_context for word in ("设备", "配置")):
                prefix = sentence[:requirement.start()]
                if "社区卫生服务中心" in prefix or "乡镇卫生院" in prefix:
                    subject = "社区卫生服务中心和乡镇卫生院"
                elif prefix in {"", "有条件者"} or prefix.endswith("条件的基层医疗卫生机构"):
                    # 同句第二个谓词或接续句沿用条款主体；不从别的文档猜主体。
                    subject = equipment_subject if prefix == "" else "基层医疗卫生机构"
                else:
                    subject = "基层医疗卫生机构"
                equipment_subject = subject
                head = term(subject, "Organization", citation)
                modality = requirement[1]
                relation = "requiresEquipment" if "应" in modality else "recommendsEquipment"
                for equipment_term in equipment:
                    if equipment_term["term"] in sentence[requirement.end():]:
                        tail = term(equipment_term["term"], "Equipment", citation)
                        edge(head, relation, tail, citation, "R-EQUIPMENT", condition=prefix,
                             modality=modality, source_section_id=section_id)

            for rule in rules.get("management_rules", []):
                if document["profile"] not in rule["profiles"]:
                    continue
                if not re.search(rule["title_pattern"], block["title"]):
                    continue
                for found in re.finditer(rule["pattern"], sentence):
                    # 证据取整句而不是截掉阈值后面的“经短期处理仍无法控制”等限制。
                    head = term(rule["head"], rule["head_type"], citation)
                    tail = term(rule["tail"], rule["tail_type"], citation)
                    condition = found.groupdict().get("condition") or sentence
                    edge(head, rule["relation"], tail, citation, rule["id"], condition=condition,
                         modality=rule.get("modality", ""), source_section_id=section_id)
                    if "interval_months" in rule:
                        thresholds.append({"id": identifier("TH-", rule["id"], block["id"], found.start()),
                                           "subject": rule["head"] + "随访间隔", "indicator": "随访间隔",
                                           "operator": "<=", "value": rule["interval_months"], "unit": "月",
                                           "context": rule["head"], "basis": block["title"],
                                           "comparison_scope": {"population": rule["head"], "purpose": "常规随访"},
                                           **citation})

        # 标题不受表格错序影响，保留首诊/随访转诊各自的整段条件，供检索后核读。
        if re.search(r"转诊", block["title"]):
            stage = "初诊" if "初诊" in text[:100] else "随访" if "随访时" in text[:100] else "通用"
            condition_id = node(identifier("N-COND-", block["id"]), f"{document['file']} §{block['section']}转诊条件",
                                "Condition", full, stage=stage, review_status="needs_review")
            action_id = term("转诊", "ManagementAction", full)
            edge(action_id, "referralWhen", condition_id, full, "R-REFERRAL-CLAUSE",
                 condition=text, review_status="needs_review", source_section_id=section_id)

        for match in re.finditer(r"(?:参见|参照|按照)《([^》]+)》", text):
            title = match[1]
            year_match = re.search(r"20\d{2}", title)
            year = year_match[0] if year_match else ""
            if title == "国家基层高血压防治管理指南" and document["profile"] == "standard":
                year = document["referenced_primary_year"]
            base_title = re.sub(r"[（(].*?[）)]", "", title)
            candidates = [d for d in documents if d["title"] == base_title and d["profile"] != "legacy"]
            exact = [d for d in candidates if year and d["year"] == year]
            status = ("resolved" if exact else "version_mismatch" if candidates and year
                      else "version_unverified" if candidates else "missing")
            # 保留完整引用句，便于人知道“引用这本指南是为了解决什么”。
            left = text.rfind("。", 0, match.start()) + 1
            right = text.find("。", match.end())
            citation = source_span(block, left, right + 1 if right >= 0 else len(text))
            ref_id = exact[0]["id"] if exact else identifier("N-REF-", base_title, year)
            node(ref_id, base_title + (f"（引用版本{year}）" if year and not exact else ""), "SourceDoc", citation,
                 loaded=bool(exact), year=year, candidate_doc_ids=[d["id"] for d in candidates])
            edge(section_id, "references", ref_id, citation, "R-EXPLICIT-REFERENCE",
                 resolution=status, requested_year=year, candidate_doc_ids=[d["id"] for d in candidates],
                 version_evidence=document["reference_year_evidence"] if document["profile"] == "standard" else citation,
                 document_available=status == "resolved", sufficient=False)
    return list(nodes.values()), list(edges.values()), thresholds
