"""数据层回归：防止章节串规则、证据丢失、版本误绑定和不同来源被去重。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.build_graph import build, extract_relations
from pipeline.document_blocks import load_blocks
from pipeline.conflict_review import review_thresholds
from tools.query_graph import Graph
from pipeline.clinical_extractor import extract_clinical
from pipeline.verification import retain_edges, preserve_previous_graph


class GraphPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = [ROOT / "data/raw" / name for name in (
            "WS-T872-2025_重排.txt", "国家基层高血压防治管理指南2025版_重排.txt",
            "中国高血压临床实践指南2025版_重排.txt")]
        cls.graph = build(cls.paths)

    def test_source_pages_sections_and_offsets(self):
        blocks = {b["id"]: b for b in self.graph["blocks"]}
        for item in [*self.graph["nodes"], *self.graph["edges"], *self.graph["thresholds"], *self.graph["threshold_candidates"]]:
            citations = item.get("evidences", [item])
            for citation in citations:
                block = blocks[citation["block_id"]]
                self.assertEqual(citation["evidence"], block["raw"][citation["start"]:citation["end"]])
                self.assertEqual(citation["page"], block["page"])
                self.assertEqual(citation["file"], block["file"])
                self.assertIsInstance(citation["page"], int)

    def test_multidocument_followup_keeps_both_sources(self):
        edges = [e for e in self.graph["edges"] if e["relation"] == "followUpEvery"]
        self.assertEqual(len(edges), 4)
        self.assertEqual({e["file"] for e in edges}, {p.name for p in self.paths[:2]})
        thresholds = [t for t in self.graph["thresholds"] if t["indicator"] == "随访间隔"]
        self.assertEqual(sorted(t["value"] for t in thresholds), [1, 1, 3, 3])

    def test_standard_references_detect_version_mismatch(self):
        refs = [e for e in self.graph["edges"] if e["relation"] == "references" and e["file"] == self.paths[0].name]
        self.assertEqual(len(refs), 4)
        self.assertEqual({e["requested_year"] for e in refs}, {"2021"})
        self.assertTrue(all(e["resolution"] == "version_mismatch" and not e["sufficient"] for e in refs))

    def test_references_heading_ends_appendix_and_keeps_original_evidence(self):
        document = self.graph["meta"]["documents"][0]
        citation = document["reference_year_evidence"]
        self.assertEqual(citation["section"], "REFERENCES")
        self.assertEqual(citation["page"], 8)
        block = next(b for b in self.graph["blocks"] if b["id"] == citation["block_id"])
        self.assertEqual(block["title"], "参考文献")
        self.assertEqual(citation["evidence"], block["raw"][citation["start"]:citation["end"]])
        self.assertIn("2021", citation["evidence"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.txt"
            path.write_text("===== 第 7 页 =====\nA.1 附录内容\n原附录\n===== 第 8 页 =====\n参 考 文 献\n1 示例参考文献\n", encoding="utf-8")
            references = load_blocks(path)[-1]
        self.assertEqual(references["section"], "REFERENCES")
        self.assertIn("1 示例参考文献", references["raw"])

    def test_missing_referenced_document(self):
        graph = build(self.paths[0])
        refs = [e for e in graph["edges"] if e["relation"] == "references"]
        self.assertEqual(len(refs), 4)
        self.assertTrue(all(e["resolution"] == "missing" and not e["candidate_doc_ids"] for e in refs))

    def test_equipment_obligation_and_subject(self):
        for path in self.paths[:2]:
            required = [e for e in self.graph["edges"] if e["file"] == path.name and e["relation"] == "requiresEquipment"]
            self.assertEqual(len(required), 7)
            recommended = [e for e in self.graph["edges"] if e["file"] == path.name and e["relation"] == "recommendsEquipment"]
            monitor = next(e for e in recommended if e["tailId"] == "N-动态血压监测仪")
            self.assertEqual(monitor["headId"], "N-社区卫生服务中心和乡镇卫生院")
            self.assertEqual(monitor["modality"], "宜")

    def test_no_summary_rules_applied_to_original_documents(self):
        self.assertFalse(any(e["rule"].startswith("R-6.") for e in self.graph["edges"]))
        self.assertTrue(any(e["rule"] == "CL-FIRST-LINE" for e in self.graph["edges"]))

    def test_filename_does_not_override_publication_year(self):
        document = self.graph["meta"]["documents"][2]
        self.assertEqual(document["year"], "2024")
        self.assertTrue(document["warnings"])

    def test_legacy_format_still_builds_without_fabricated_pages(self):
        path = ROOT / "data/processed/中国高血压临床实践指南2025版_知识库文档_重排.txt"
        graph = build(path)
        self.assertTrue(any(e["relation"] == "preferredFor" for e in graph["edges"]))
        self.assertTrue(all(b["page"] is None for b in graph["blocks"]))

    def test_numbered_heading_and_continuation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.txt"
            path.write_text("===== 第 1 页 =====\n8.4.2 初诊时\n条件甲\n===== 第 2 页 =====\n条件乙\n8.3 年度评估\n每年评估\n", encoding="utf-8")
            blocks = load_blocks(path)
        self.assertEqual([(b["section"], b["page"]) for b in blocks], [("8.4.2", 1), ("8.4.2", 2), ("8.3", 2)])

    def test_identity_and_provenance_stable_on_rebuild(self):
        again = build(self.paths)
        self.assertEqual(self.graph["nodes"], again["nodes"])
        self.assertEqual(self.graph["edges"], again["edges"])
        self.assertEqual(self.graph["thresholds"], again["thresholds"])

    def test_numeric_difference_is_not_automatically_true_conflict(self):
        items = [{"subject": "示例", "indicator": "示例指标", "unit": "示例单位", "context": "",
                  "operator": ">=", "value": value, "file": name}
                 for value, name in [(10, "a"), (20, "b")]]
        review = review_thresholds(items)
        self.assertEqual(review["hard"], [])
        self.assertEqual(len(review["candidates"]), 1)

    def test_unreviewed_numbers_retained_and_explicit_bp_rule_remains_pending(self):
        self.assertTrue(self.graph["threshold_candidates"])
        bp = [t for t in self.graph["thresholds"] if t.get("decision_rule_id")]
        self.assertEqual({t["role"]: t["value"] for t in bp}, {"sbp": 140, "dbp": 90})
        self.assertTrue(all(t["verification"] == "pending" and t["derived_from"] for t in bp))
        rule = self.graph["decision_rules"][0]
        self.assertEqual(rule["logic"], "OR")
        self.assertEqual(rule["requirements"]["minimum_visits"], 3)
        self.assertEqual(rule["requirements"]["maximum_days"], 28)
        self.assertFalse(rule["sufficient"])

    def test_disordered_standard_pages_do_not_claim_reliable_section(self):
        blocks = [b for b in self.graph["blocks"] if b["file"] == self.paths[0].name and b["page"] in {4, 6}]
        self.assertTrue(blocks)
        self.assertTrue(all(b["section_status"] == "needs_layout_review" for b in blocks))

    def test_matching_document_is_not_sufficient_passage_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            standard = Path(folder) / "standard.txt"
            guideline = Path(folder) / "guideline.txt"
            standard.write_text("===== 第 1 页 =====\nWS/T 872—2025\n1 范围\n具体参见《国家基层高血压防治管理指南（2021）》。", encoding="utf-8")
            guideline.write_text("===== 第 1 页 =====\n国家基层高血压防治管理指南（2021）\n1 管理要求\n示例内容", encoding="utf-8")
            graph = build([standard, guideline])
        ref = next(e for e in graph["edges"] if e["relation"] == "references")
        self.assertEqual(ref["resolution"], "resolved")
        self.assertTrue(ref["document_available"])
        self.assertFalse(ref["sufficient"])

    def test_reference_query_explains_insufficient_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "graph.json"
            path.write_text(json.dumps(self.graph, ensure_ascii=False), encoding="utf-8")
            rows = Graph(path).reference_status("WS-T872")
        self.assertEqual(len(rows), 4)
        self.assertTrue(all("版本不同" in row["message"] for row in rows))

    def test_every_automatic_record_is_pending_with_confidence(self):
        for key in ("nodes", "edges", "thresholds", "threshold_candidates", "edge_candidates",
                    "entity_candidates", "extraction_candidates", "blocks", "decision_rules"):
            for record in self.graph[key]:
                self.assertEqual(record["verification"], "pending", (key, record["id"]))
                self.assertIsInstance(record["confidence"], (int, float))
                self.assertTrue(0 <= record["confidence"] <= 1)
        self.assertTrue(self.graph["entity_candidates"])
        self.assertTrue(self.graph["extraction_candidates"])
        self.assertEqual(self.graph["discarded"], [])

    def test_orphan_or_missing_evidence_assertions_are_preserved_whole(self):
        proposal = {"id": "uncertain", "headId": "missing", "tailId": "also_missing",
                    "relation": "example", "evidence": "", "condition": "原始条件",
                    "extra_payload": {"keep": "完整保留"}}
        kept, candidates = retain_edges([proposal], {})
        self.assertEqual(kept, [])
        self.assertEqual(len(candidates), 1)
        for key, value in proposal.items():
            self.assertEqual(candidates[0][key], value)
        self.assertEqual(candidates[0]["verification"], "pending")
        self.assertIn("evidence_missing", candidates[0]["validation_errors"])

    def test_partially_matching_legacy_rule_is_retained(self):
        block = next(b for b in self.graph["blocks"] if b["file"] == self.paths[0].name and b["section"] == "4.2")
        rule = {"id": "partial", "section": "4.2", "head": "未建节点", "relation": "requiresDrugClass",
                "tail": "利尿剂", "require_all": ["降压药", "不存在的锚点"], "evidence_from": "也不存在"}
        edges, candidates = extract_relations([block], {"rules": [rule]}, set(), block["file"])
        self.assertEqual(edges, [])
        self.assertEqual(candidates[0]["proposed_rule"], rule)
        self.assertEqual(candidates[0]["verification"], "pending")
        self.assertIn("不存在的锚点", candidates[0]["missing_terms"])

    def test_drug_rules_produce_evidence_from_all_three_documents(self):
        clinical = [e for e in self.graph["edges"] if e.get("extraction_basis") == "全文规则"]
        self.assertEqual({e["file"] for e in clinical}, {p.name for p in self.paths})
        self.assertTrue(any(e["rule"] == "PR-A-INDICATIONS" and e["section"] == "5.4.2" for e in clinical))
        self.assertTrue(any(e["rule"] == "PR-MI-INITIAL" and e["section"] == "5.4.3.2" for e in clinical))

    def test_stock_selection_and_first_line_are_distinct(self):
        standard = [e for e in self.graph["edges"] if e["file"] == self.paths[0].name and e.get("extraction_basis") == "全文规则"]
        self.assertEqual({e["relation"] for e in standard}, {"requiresDrugClass"})
        first_line = [e for e in self.graph["edges"] if e["relation"] == "firstLineFor"]
        self.assertEqual(len(first_line), 4)
        self.assertTrue(all(e["file"] == self.paths[2].name and e["section"] == "CQ13" for e in first_line))
        beta_primary = [e for e in self.graph["edges"] if e["headId"] == "N-β受体阻滞剂" and e["file"] == self.paths[1].name]
        self.assertTrue(any(e["relation"] == "recommendedFor" for e in beta_primary))
        self.assertFalse(any(e["relation"] == "excludedFromFirstLine" for e in beta_primary))

    def test_regimen_preserves_joint_use_and_one_of_group(self):
        regimen = next(n for n in self.graph["nodes"] if n["type"] == "DrugRegimen" and n["attributes"]["codes"] == "A+B")
        components = regimen["attributes"]["components"]
        self.assertEqual(components[0]["selection"], "one_of")
        self.assertEqual(set(components[0]["options"]), {"血管紧张素转换酶抑制剂", "血管紧张素II受体阻滞剂"})
        edge = next(e for e in self.graph["edges"] if e["rule"] == "PR-MI-INITIAL" and e["relation"] == "preferredRegimenFor")
        self.assertEqual(edge["headId"], regimen["id"])
        self.assertIn("小剂量", edge["condition"])
        self.assertTrue(edge["supporting_evidence"])

    def test_primary_stock_retains_limited_resource_alternative(self):
        stock = [e for e in self.graph["edges"] if e["rule"] == "PR-DRUG-STOCK"]
        alternatives = [e for e in stock if e["tailId"] in {"N-血管紧张素转换酶抑制剂", "N-血管紧张素II受体阻滞剂"}]
        self.assertEqual(len(alternatives), 2)
        self.assertTrue(all(e["relation"] == "recommendsDrugClass" for e in alternatives))
        self.assertTrue(all("无条件者至少配备其中一种" in e["condition"] for e in alternatives))

    def test_displaced_dm_ckd_statements_keep_physical_and_semantic_locations(self):
        edges = [e for e in self.graph["edges"] if e["rule"] in {"PR-COMORBID-DM", "PR-COMORBID-CKD"}
                 and e["relation"] == "preferredFor"]
        self.assertEqual(len(edges), 4)
        for edge in edges:
            self.assertEqual((edge["page"], edge["section"], edge["semantic_section"]), (9, "5.4.6.1", "5.4.3.2"))
            self.assertEqual(edge["verification"], "pending")
            self.assertLessEqual(edge["confidence"], 0.55)
            self.assertTrue(any(c["section"] == "5.4.2" for c in edge["supporting_evidence"]))

    def test_gout_contraindication_does_not_expand_to_all_diuretics(self):
        edges = [e for e in self.graph["edges"] if e["rule"] == "PR-THIAZIDE-GOUT"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["headId"], "N-噻嗪类利尿剂")

    def test_interaction_exception_and_creatinine_condition_survive(self):
        interaction = next(e for e in self.graph["edges"] if e["rule"] == "PR-ARNI-INTERACTIONS" and e["tailId"] == "N-血管紧张素II受体阻滞剂")
        self.assertIn("相同成分的ARB除外", interaction["exceptions"])
        contraindications = [e for e in self.graph["edges"] if e["rule"] == "PR-A-CONTRAINDICATIONS"]
        self.assertTrue(contraindications)
        self.assertTrue(all("血肌酐≥3mg/dl" in e["condition"] for e in contraindications))

    def test_missing_code_definition_keeps_unresolved_proposal(self):
        block = next(b for b in self.graph["blocks"] if b["file"] == self.paths[1].name and "合并心肌梗死：首选" in b["raw"].replace(" ", ""))
        config = json.loads((ROOT / "ontology/clinical_relation_rules.json").read_text(encoding="utf-8"))
        _, edges, candidates = extract_clinical([block], {"profile": "primary"}, config)
        self.assertFalse(any(e["rule"] == "PR-MI-INITIAL" for e in edges))
        unresolved = [c for c in candidates if c.get("kind") == "unresolved_drug_regimen"]
        self.assertTrue(unresolved)
        self.assertEqual(unresolved[0]["verification"], "pending")

    def test_numeric_candidates_exist_for_each_full_document(self):
        self.assertEqual({t["file"] for t in self.graph["threshold_candidates"]}, {p.name for p in self.paths})

    def test_two_hop_dm_path_joins_only_same_regimen_and_definition(self):
        first = next(e for e in self.graph["edges"] if e["rule"] == "PR-COMORBID-DM"
                     and e["relation"] == "preferredRegimenFor")
        self.assertEqual(first["tailId"], "N-高血压合并糖尿病患者")
        second = [e for e in self.graph["edges"] if e.get("regimen_group") == first["regimen_group"]
                  and e["relation"] == "hasAlternativeComponent"]
        self.assertEqual(len(second), 2)
        self.assertTrue(all(e["section"] == "5.4.2" and e["combination_limit_evidence"] for e in second))
        self.assertEqual(first["semantic_section"], "5.4.3.2")
        self.assertTrue(first["combination_limit_evidence"])
        self.assertFalse(any(e["relation"] == "complicates" and e["headId"] == "N-高血压"
                             for e in self.graph["edges"]))

    def test_bp_rule_requires_agreement_of_prose_and_explicit_or_boundary(self):
        from pipeline.decision_extractor import extract_decisions
        config = json.loads((ROOT / "ontology/decision_rules.json").read_text(encoding="utf-8"))
        block = next(b for b in self.graph["blocks"] if b["file"] == self.paths[1].name and b["section"] == "4.2.1")
        for raw in [block["raw"].replace("和 ( 或 )", "且"), block["raw"].replace("140/90", "130/80")]:
            thresholds, decisions = extract_decisions([{**block, "raw": raw}], {"profile": "primary"}, config)
            self.assertEqual((thresholds, decisions), ([], []))

    def test_rebuild_archives_removed_pending_results_and_source_blocks(self):
        previous = {"meta": {"built_at": "old"}, "edge_candidates": [{"id": "old-pending", "verification": "pending", "confidence": 0.1}],
                    "blocks": [{"id": "old-block", "raw": "必须保留的原文"}]}
        current = {"meta": {"built_at": "new"}, "edge_candidates": [], "blocks": []}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "graph.json"
            path.write_text(json.dumps(previous, ensure_ascii=False), encoding="utf-8")
            preserve_previous_graph(current, path)
            snapshot = Path(current["meta"]["history_snapshots"][0]["path"])
            self.assertEqual(json.loads(snapshot.read_text(encoding="utf-8")), previous)
            path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
            again = {"meta": {"built_at": "newer"}, "edge_candidates": [], "blocks": []}
            preserve_previous_graph(again, path)
            self.assertEqual(again["meta"]["history_snapshots"], current["meta"]["history_snapshots"])


if __name__ == "__main__":
    unittest.main()
