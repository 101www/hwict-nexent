"""真实HTTP/SSE验收三类能力，并保存完整输入输出；不会修改图谱或伪造模型回答。"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "java-mcp"))
from mcp_client import McpClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8081/sse")
    parser.add_argument("--out", default="docs/validation/reasoning-mcp-acceptance.json")
    args = parser.parse_args()
    client = McpClient(args.url)
    report = {"tested_at": datetime.now().astimezone().isoformat(), "endpoint": args.url,
              "kind": "actual_mcp_responses_not_llm_answers", "cases": []}

    def run(name, tool, parameters, verify):
        result = client.call(tool, parameters)
        verify(result)
        report["cases"].append({"name": name, "tool": tool, "arguments": parameters, "result": result, "passed": True})
        print("PASS", name)

    def check_dm(row):
        assert row["total"] == 1
        item = row["items"][0]
        assert len(item["paths"]) == 2
        assert all(p["hops"] == 2 for p in item["paths"])
        assert item["components"][0]["selection"] == "one_of"
        assert not row["sufficient"]

    def check_status(row):
        assert row["mode"] == "real_graph_snapshot"
        assert row["nodes"] >= 324

    def check_conflicts(row):
        assert row["total"] == 2
        assert all(r["status"] == "not_conflicting_different_purpose" for r in row["items"])

    def check_bp(row, reached, scope="method_unconfirmed"):
        assert row["reference_boundary_reached"] == reached
        assert row["scope_status"] == scope
        assert row["protocol_status"] != "reported_conditions_match_pending_rule"
        assert row["sufficient"] is False

    run("图谱快照", "graph_status", {}, check_status)
    run("糖尿病两跳择一方案", "resolve_regimen", {"population": "高血压合并糖尿病患者"}, check_dm)
    run("配备与初始治疗不同目的", "detect_conflicts", {"subject": "β受体阻滞剂", "limit": 10}, check_conflicts)
    for s, d, reached in [(140,90,True), (140,89,True), (139,90,True), (139,89,False)]:
        run(f"边界{s}/{d}", "evaluate_blood_pressure", {"systolic":s, "diastolic":d, "unit":"mmHg",
            "measurement_method":"unknown"}, lambda row, v=reached: check_bp(row,v))
    run("家庭测量不套诊室条款", "evaluate_blood_pressure", {"systolic":140,"diastolic":90,"unit":"mmHg",
        "measurement_method":"home"}, lambda row: check_bp(row,None,"measurement_method_mismatch"))
    report["all_passed"] = True
    target = ROOT / args.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n", encoding="utf-8")
    print("Saved", target)


if __name__ == "__main__":
    main()
