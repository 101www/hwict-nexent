"""从三份全文按各自语义抽取；字母方案由基层指南原文定义解析，不复用摘要节号。"""
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


def extract_clinical(blocks: list[dict], document: dict, config: dict) -> tuple[list[dict], list[dict], list[dict]]:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    candidates: list[dict] = []
    profile = document["profile"]
    prepared = [(b, compact(b["raw"])[0]) for b in blocks]
    # 代号必须有本文件中的定义证据；缺定义时保存未解析方案候选。
    definitions = []
    combination_limits = []
    if profile == "primary":
        for block, text in prepared:
            if block["section"] == "5.4.2" and "A：ACEI和ARB" in text:
                definitions.append(source_span(block, 0, len(text)))
            for match in re.finditer("不宜联合应用ACEI与ARB。", text):
                combination_limits.append(source_span(block, match.start(), match.end()))

    def node(name: str, typ: str, citation: dict, attributes: dict | None = None) -> str:
        nid = "N-" + name
        if nid not in nodes:
            nodes[nid] = pending({"id": nid, "name": name, "type": typ, "aliases": [],
                                  "attributes": attributes or {}, **citation, "evidences": [citation],
                                  "sections": [citation["section"]]}, 0.9, "automatic_extraction")
        elif citation not in nodes[nid]["evidences"]:
            nodes[nid]["evidences"].append(citation)
        return nid

    for block, text in prepared:
        matched_ranges: list[tuple[int, int]] = []
        for rule in config["rules"]:
            if profile not in rule["profiles"]:
                continue
            scope = config.get("scopes", {}).get(rule.get("scope", ""))
            spans = [(0, len(text))]
            if scope:
                spans = [(m.start(), m.end()) for m in re.finditer(scope, text, re.S)]
            for scope_start, scope_end in spans:
                for match in re.finditer(rule["pattern"], text[scope_start:scope_end], re.S):
                    start, end = scope_start + match.start(), scope_start + match.end()
                    citation = source_span(block, start, end)
                    matched_ranges.append((start, end))
                    condition = rule.get("condition", "")
                    if condition:
                        condition += "；"
                    condition += compact(citation["evidence"])[0]
                    reasons = ["clinical_review_required"]
                    extra = {"scope": rule.get("clinical_scope", {}),
                             "basis_sections": rule.get("basis_sections", []),
                             "source_profile": profile, "modality": rule.get("modality", ""),
                             "source_section_id": "N-" + block["id"],
                             "extraction_basis": "全文规则"}
                    expected = rule.get("section_prefix")
                    if expected and not block["section"].startswith(expected):
                        extra["semantic_section"] = expected
                        extra["section_status"] = "needs_layout_review"
                        reasons.append("sentence_displaced_from_expected_section")
                    if scope:
                        extra["supporting_evidence"] = [source_span(block, scope_start, scope_end)]
                    if rule.get("uses_codes"):
                        if not definitions:
                            candidates.append(pending({"id": identifier("C-", rule["id"], block["id"], start),
                                                       "kind": "unresolved_drug_codes", "rule": rule["id"],
                                                       "proposed_facts": rule["facts"], "condition": condition,
                                                       **citation}, 0.3, "letter_code_definition_missing"))
                            continue
                        extra["supporting_evidence"] = definitions
                        if combination_limits:
                            extra["combination_limit_evidence"] = combination_limits
                    for fact in rule.get("facts", []):
                        head = node(fact["head"], fact.get("head_type", "DrugClass"), citation)
                        tail = node(fact["tail"], fact.get("tail_type", "Disease"), citation)
                        eid = identifier("E-", rule["id"], head, fact["relation"], tail, block["id"], start)
                        edges.append(pending({"id": eid, "headId": head, "relation": fact["relation"],
                                              "tailId": tail, "condition": condition, "rule": rule["id"],
                                              **citation, **extra, "choice_group": rule.get("choice_group", ""),
                                              "exceptions": rule.get("exceptions", [])},
                                             rule.get("confidence", 0.9), *reasons))
                    for specification in rule.get("regimens", []):
                        if not definitions:
                            candidates.append(pending({"id": identifier("C-", rule["id"], block["id"], start, specification["codes"]),
                                                       "kind": "unresolved_drug_regimen", "rule": rule["id"],
                                                       "codes": specification["codes"], "condition": condition,
                                                       **citation}, 0.3, "letter_code_definition_missing"))
                            continue
                        codes = specification["codes"].split("+")
                        components = [{"code": code, "options": config["drug_codes"][code], "selection": "one_of"}
                                      for code in codes]
                        name = " + ".join("或".join(c["options"]) for c in components)
                        regimen = node(name, "DrugRegimen", citation,
                                       {"components": components, "selection": "all_components", "codes": specification["codes"]})
                        target = node(specification["tail"], specification.get("tail_type", "Disease"), citation)
                        relation = specification.get("relation", "preferredRegimenFor")
                        group = identifier("RG-", rule["id"], block["id"], start, name)
                        edges.append(pending({"id": identifier("E-", group, relation, target), "headId": regimen,
                                              "relation": relation, "tailId": target, "condition": condition,
                                              "rule": rule["id"], **citation, **extra,
                                              "supporting_evidence": definitions, "regimen_group": group}, 0.88, *reasons))
                        for component in components:
                            for option in component["options"]:
                                drug = node(option, "DrugClass", citation)
                                component_relation = "hasAlternativeComponent" if len(component["options"]) > 1 else "hasComponent"
                                # 第二跳真正引用代号定义，而不是再次引用“首选A”冒充独立证据。
                                definition = definitions[0]
                                edges.append(pending({"id": identifier("E-", group, drug), "headId": regimen,
                                                      "relation": component_relation, "tailId": drug,
                                                      "condition": condition, "rule": rule["id"], **citation,
                                                      **definition,
                                                      "option_group": component["code"], "regimen_group": group,
                                                      "supporting_evidence": definitions,
                                                      "combination_limit_evidence": combination_limits}, 0.88, *reasons))

        # 无结构化规则覆盖的药物语句和表格片段同样保留；不从共现关系编造推荐/禁忌。
        if profile in {"standard", "primary", "clinical"}:
            for match in re.finditer(r"[^。！？]+[。！？]?", text):
                sentence = match[0]
                if not re.search(config["candidate_drug_pattern"], sentence):
                    continue
                if not re.search(config["candidate_relation_pattern"], sentence):
                    continue
                # 已匹配语句仍存原文候选，供核验未被结构化的限制条件。
                citation = source_span(block, match.start(), match.end())
                candidates.append(pending({"id": identifier("C-DRUG-", block["id"], match.start(), match.end()),
                                           "kind": "drug_statement", **citation,
                                           "matched_rule_ranges": [[a, b] for a, b in matched_ranges
                                                                   if a < match.end() and b > match.start()],
                                           "reason": "原文片段待核读，保留条件、表格关系和未覆盖语义"}, 0.4, "statement_requires_review"))
    return list(nodes.values()), edges, candidates
