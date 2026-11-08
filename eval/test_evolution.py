"""版本审核/发布的防回归测试。小型合成夹具仅测生命周期，不充当医学证据。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.evolution import EvolutionStore, changes, digest, read, validate, write


def pending(**values):
    return {**values, "verification": "pending", "confidence": 0.5,
            "confidence_basis": "synthetic_test_fixture"}


class EvolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.doc = self.root / "synthetic_fixture.txt"
        self.doc.write_text("合成测试原文甲", encoding="utf-8")
        self.schema = {"version": "test-1", "entity_types": [{"name": "Disease"}],
                       "relation_types": [{"name": "relatedTo", "head": "Disease", "tail": "Disease"}]}
        self.schema_path = self.root / "ontology.json"
        write(self.schema_path, self.schema)
        citation = {"file": self.doc.name, "page": 1, "section": "1", "block_id": "B1",
                    "start": 0, "end": 7, "evidence": "合成测试原文甲"}
        self.graph = {"meta": {"ontology_version": "test-1", "source_docs": [self.doc.name]},
                      "nodes": [pending(id="N1", name="甲", type="Disease", **citation),
                                pending(id="N2", name="乙", type="Disease", **citation)],
                      "edges": [pending(id="E1", headId="N1", tailId="N2", relation="relatedTo", **citation)],
                      "blocks": [pending(id="B1", raw="合成测试原文甲", file=self.doc.name, page=1, section="1")],
                      "thresholds": [], "decision_rules": [], "discarded": [],
                      "threshold_candidates": [pending(id="C1", kind="synthetic_candidate", **citation)],
                      "entity_candidates": [], "edge_candidates": [], "extraction_candidates": []}
        self.store = EvolutionStore(self.root / "store")
        self.initial = self.store.initialize(self.graph, self.schema, [self.doc], "合成基线")

    def propose(self, graph=None, schema=None):
        if schema:
            write(self.schema_path, schema)
        with patch("pipeline.build_graph.build", return_value=copy.deepcopy(graph or self.graph)):
            return self.store.propose([], "合成生命周期测试", self.schema_path)

    def approve(self, pid):
        return self.store.review(pid, "approve", "automated_test", "测试夹具，不是人工审核", "automated_test")

    def publish(self, pid):
        self.approve(pid)
        return self.store.publish(pid, allow_test_review=True)

    def test_approval_required_for_pending_deferred_and_rejected(self):
        p = self.propose()
        for decision in (None, "defer", "reject"):
            if decision:
                self.store.review(p["id"], decision, "automated_test", "测试动作", "automated_test")
            with self.assertRaises(ValueError):
                self.store.publish(p["id"], allow_test_review=True)
        self.assertEqual(len(self.store.state()["releases"]), 1)

    def test_test_actor_cannot_publish_without_explicit_flag(self):
        p = self.propose()
        self.approve(p["id"])
        with self.assertRaisesRegex(ValueError, "自动测试"):
            self.store.publish(p["id"])
        result = self.store.publish(p["id"], allow_test_review=True)
        g = self.store.bundle(self.store.folder("releases", result["release_id"]))["graph"]
        self.assertEqual(g["meta"]["evolution"]["review_actor_kind"], "automated_test")
        self.assertTrue(all(e["verification"] == "pending" for e in g["edges"]))

    def test_tampered_candidate_after_approval_is_blocked(self):
        p = self.propose()
        self.approve(p["id"])
        file = self.store.folder("proposals", p["id"]) / "graph.json"
        changed = read(file)
        changed["edges"][0]["relation"] = "fabricatedRelation"
        write(file, changed)
        with self.assertRaisesRegex(ValueError, "损坏"):
            self.store.publish(p["id"], allow_test_review=True)

    def test_tampered_diff_or_validation_is_blocked(self):
        p = self.propose()
        file = self.store.folder("proposals", p["id"]) / "proposal.json"
        changed = read(file)
        changed["validation"]["passed"] = False
        write(file, changed)
        with self.assertRaisesRegex(ValueError, "重新生成"):
            self.approve(p["id"])

    def test_stale_base_cannot_overwrite_new_release(self):
        first, second = self.propose(), self.propose()
        current = self.publish(first["id"])
        self.approve(second["id"])
        with self.assertRaisesRegex(ValueError, "过期"):
            self.store.publish(second["id"], allow_test_review=True)
        self.assertEqual(self.store.state()["current"], current["release_id"])

    def test_invalid_evidence_and_endpoints_prevent_approval(self):
        candidate = copy.deepcopy(self.graph)
        candidate["edges"][0].update(tailId="N-MISSING", evidence="错误原文")
        p = self.propose(candidate)
        self.assertFalse(p["validation"]["passed"])
        self.assertTrue(any("端点不存在" in e for e in p["validation"]["errors"]))
        self.assertTrue(any("证据" in e for e in p["validation"]["errors"]))
        with self.assertRaisesRegex(ValueError, "校验未通过"):
            self.approve(p["id"])

    def test_unknown_schema_types_and_endpoint_constraints_checked(self):
        candidate = copy.deepcopy(self.graph)
        candidate["nodes"][0]["type"] = "Unknown"
        report = validate(candidate, self.schema)
        self.assertFalse(report["passed"])
        self.assertTrue(any("未定义实体类型" in e for e in report["errors"]))
        self.assertTrue(any("不满足" in e for e in report["errors"]))
        self.assertEqual(report["ontology_proposals"][0]["name"],"Unknown")
        self.assertEqual(report["ontology_proposals"][0]["verification"],"pending")

    def test_pending_cannot_be_silently_promoted(self):
        candidate = copy.deepcopy(self.graph)
        candidate["edges"][0]["verification"] = "verified"
        p = self.propose(candidate)
        self.assertFalse(p["validation"]["passed"])

    def test_missing_and_modified_candidates_preserved_in_full(self):
        candidate = copy.deepcopy(self.graph)
        candidate["threshold_candidates"] = []
        candidate["nodes"][0]["name"] = "甲的修订名称"
        p = self.propose(candidate)
        result = self.publish(p["id"])
        graph = self.store.bundle(self.store.folder("releases", result["release_id"]))["graph"]
        retained = graph["evolution_retained"]
        self.assertTrue(any(r["record"] == self.graph["threshold_candidates"][0] for r in retained))
        self.assertTrue(any(r["record"] == self.graph["nodes"][0] for r in retained))
        baseline = self.store.bundle(self.store.folder("releases", self.initial["release_id"]))["graph"]
        self.assertEqual(baseline["threshold_candidates"], self.graph["threshold_candidates"])
        self.assertEqual(graph["discarded"], [])

    def test_rollback_restores_snapshot_without_deleting_future_release(self):
        p = self.propose()
        result = self.publish(p["id"])
        self.store.rollback(self.initial["release_id"], "automated_test", "合成回滚测试", "automated_test")
        self.assertEqual(self.store.state()["current"], self.initial["release_id"])
        self.assertTrue(self.store.folder("releases", result["release_id"]).is_dir())
        self.assertEqual(len(self.store.state()["events"]), 5)

    def test_changed_source_requires_explicit_resubmission(self):
        self.doc.write_text("内容改变",encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "显式"):
            self.propose()

    def test_source_change_during_build_is_blocked(self):
        def changed(*args):
            self.doc.write_text("并发改变",encoding="utf-8")
            return copy.deepcopy(self.graph)
        with patch("pipeline.build_graph.build", side_effect=changed):
            with self.assertRaisesRegex(ValueError,"建图期间"):
                self.store.propose([],"并发测试",self.schema_path)

    def test_schema_change_requires_new_version(self):
        schema = copy.deepcopy(self.schema)
        schema["entity_types"].append({"name":"SyntheticNewType"})
        with self.assertRaisesRegex(ValueError,"版本号"):
            self.propose(schema=schema)
        schema["version"] = "test-2"
        p = self.propose(schema=schema)
        self.assertTrue(p["diff"]["ontology_changed"])
        self.assertEqual(p["diff"]["ontology"]["entity_types"]["added"],["SyntheticNewType"])
        result = self.publish(p["id"])
        self.assertEqual(self.store.bundle(self.store.folder("releases",result["release_id"]))["ontology"],schema)

    def test_publish_uses_reviewed_rule_files_not_new_disk_state(self):
        p = self.propose()
        folder = self.store.folder("proposals",p["id"])
        name = "ontology__clinical_relation_rules.json"
        expected = digest((folder/name).read_bytes())
        result = self.publish(p["id"])
        published = self.store.folder("releases",result["release_id"])
        self.assertEqual(digest((published/name).read_bytes()),expected)

    def test_writer_lock_and_path_traversal_guard(self):
        with self.store.locked():
            with self.assertRaisesRegex(ValueError,"正在写入"):
                self.propose()
        with self.assertRaisesRegex(ValueError,"非法"):
            self.store.proposal("../state")

    def test_published_review_cannot_be_rewritten(self):
        p = self.propose()
        self.publish(p["id"])
        with self.assertRaisesRegex(ValueError,"已发布"):
            self.store.review(p["id"],"reject","automated_test","测试","automated_test")


if __name__ == "__main__":
    unittest.main()
