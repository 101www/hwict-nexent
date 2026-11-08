"""通过 MCP 协议验证真实图谱，不需要 Nexent 登录或模型 API。

    python java-mcp/test_real_graph_mcp.py --report docs/validation/mcp_smoke_report.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp_client import McpClient


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(client: McpClient, report: dict) -> None:
    report["server"] = client.server
    tools = client.list_tools()
    report["tools"] = tools
    expected = {"graph_status", "find_entities", "query_relations", "traverse_relations", "lookup_clause",
                "get_evidence", "check_references", "query_candidates", "compare_threshold", "detect_conflicts",
                "resolve_regimen", "evaluate_blood_pressure"}
    require({t["name"] for t in tools} == expected, "实际工具清单不匹配")
    for tool in tools:
        require(tool.get("inputSchema", {}).get("type") == "object", "工具缺少参数 schema")
    print(f"工具发现通过：{len(tools)} 个工具")

    def call(name: str, arguments: dict) -> dict:
        value = client.call(name, arguments)
        require(value.get("sufficient") is False, f"{name} 不应自动宣称证据充分")
        report["calls"].append({"tool": name, "arguments": arguments, "result": value})
        return value

    status = call("graph_status", {})
    require(status["mode"] == "real_graph_snapshot", "仍在使用演示数据")
    require(len(status["meta"]["documents"]) == 3, "未加载三份真实文档")

    entities = call("find_entities", {"keyword": "顽固性高血压", "type": "Disease"})
    require(any(n["name"] == "难治性高血压" for n in entities["items"]), "别名检索失败")

    relations = call("query_relations", {"keyword": "followUpEvery", "limit": 10})
    require(relations["total"] == 4, "未返回两个来源的随访关系")
    require(len({e["file"] for e in relations["items"]}) == 2, "不同文档证据被合并或丢失")
    require(all(e["verification"] == "pending" and "confidence" in e for e in relations["items"]), "核验状态丢失")

    edge = relations["items"][0]
    evidence = call("get_evidence", {"block_id": edge["block_id"]})["items"][0]
    require(evidence["raw"][edge["start"]:edge["end"]] == edge["evidence"], "证据与原文偏移不一致")

    clauses = call("lookup_clause", {"keyword": "随访频率", "standard": "国家基层"})
    require(clauses["total"] > 0, "无法检索原文块")

    references = call("check_references", {"keyword": "WS/T 872—2025", "limit": 10})
    require(references["total"] == 4, "引用数量不符")
    require(all(r["resolution"] == "version_mismatch" for r in references["items"]), "版本不匹配未标记")
    require(all(r["version_evidence"]["section"] == "REFERENCES" for r in references["items"]), "参考文献章节未修正")

    paths = call("traverse_relations", {"start_entity": "随访", "relation": "followUpEvery", "hops": 1,
                                         "end_entity": "血压达标患者", "limit": 10})
    require(len(paths["paths"]) == 2, "反向遍历或多来源路径丢失")
    require(all(not p["sufficient"] and not p["steps"][0]["forward"] for p in paths["paths"]), "路径方向或充分性错误")

    first = call("query_candidates", {"keyword": "", "collection": "extraction_candidates", "limit": 2})
    second = call("query_candidates", {"keyword": "", "collection": "extraction_candidates", "limit": 2, "offset": 2})
    require(first["truncated"] and second["offset"] == 2, "候选翻页失败")
    require(first["items"][0] != second["items"][0], "翻页返回重复起点")

    compared = call("compare_threshold", {"subject": "血压达标患者", "value": 4, "unit": "月"})
    require(compared["total"] == 2 and all(r["matches"] is False for r in compared["items"]), "数值比较错误")
    differences = call("detect_conflicts", {})
    require(differences["total"] == 2 and all(r["status"] == "not_conflicting_different_purpose"
            for r in differences["items"]), "应返回两个有原文依据的不同目的对照，不能制造指南真冲突")

    regimen = call("resolve_regimen", {"population": "高血压合并糖尿病患者"})
    require(regimen["total"] == 1 and all(p["hops"] == 2 for p in regimen["items"][0]["paths"]), "两跳方案组合失败")
    bp = call("evaluate_blood_pressure", {"systolic": 140, "diastolic": 90, "unit": "mmHg", "measurement_method": "unknown"})
    require(bp["reference_boundary_reached"] and bp["protocol_status"] == "insufficient_or_unmet_conditions", "不能把单次边界命中当作确诊")

    missing = call("find_entities", {"keyword": "不存在的测试实体xyz"})
    require(missing["total"] == 0 and "不能据此" in missing["message"], "未命中提示错误")
    report["passed"] = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8081/sse")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = {"tested_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
              "url": args.url, "scope": "Java MCP protocol and real graph; Nexent/model not exercised",
              "passed": False, "calls": []}
    try:
        run(McpClient(args.url), report)
        print(f"\n通过：真实图谱的 {len(report['calls'])} 次 MCP 工具调用。尚未验证 Nexent 中的模型调用。")
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"\n失败：{report['error']}")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"验证记录：{args.report.resolve()}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
