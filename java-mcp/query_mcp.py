"""通过真正的 HTTP/SSE MCP 协议查询 Java 服务，不直接读取 graph.json。

在项目根目录执行：
    python java-mcp/query_mcp.py status
    python java-mcp/query_mcp.py relations 随访
    python java-mcp/query_mcp.py references WS-T872
    python java-mcp/query_mcp.py clause 随访频率 --file 国家基层
"""
from __future__ import annotations

import argparse
import json

from mcp_client import McpClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "entities", "relations", "references", "clause", "evidence", "candidates", "path", "conflicts", "regimen", "bp"])
    parser.add_argument("keyword", nargs="?", default="")
    parser.add_argument("--url", default="http://127.0.0.1:8081/sse")
    parser.add_argument("--file", default="")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--hops", type=int, default=2)
    parser.add_argument("--end", default="")
    parser.add_argument("--sbp", type=float, default=140)
    parser.add_argument("--dbp", type=float, default=90)
    parser.add_argument("--method", default="unknown", choices=["unknown", "office", "home", "ambulatory"])
    args = parser.parse_args()
    page = {"limit": args.limit, "offset": args.offset}
    tool, parameters = {
        "status": ("graph_status", {}),
        "entities": ("find_entities", {"keyword": args.keyword, **page}),
        "relations": ("query_relations", {"keyword": args.keyword, "file": args.file, **page}),
        "references": ("check_references", {"keyword": args.keyword, **page}),
        "clause": ("lookup_clause", {"keyword": args.keyword, "standard": args.file, **page}),
        "evidence": ("get_evidence", {"block_id": args.keyword}),
        "candidates": ("query_candidates", {"keyword": args.keyword, **page}),
        "path": ("traverse_relations", {"start_entity": args.keyword, "end_entity": args.end, "hops": args.hops, "limit": args.limit}),
        "conflicts": ("detect_conflicts", {"subject": args.keyword, **page}),
        "regimen": ("resolve_regimen", {"population": args.keyword}),
        "bp": ("evaluate_blood_pressure", {"systolic": args.sbp, "diastolic": args.dbp,
                                             "unit": "mmHg", "measurement_method": args.method}),
    }[args.command]
    try:
        result = McpClient(args.url).call(tool, parameters)
    except (RuntimeError, TimeoutError, OSError) as exc:
        print(f"查询失败：{exc}")
        print("请先启动 Java 的 McpServerApplication，再运行此命令。")
        return 1
    print(f"\n实际调用 MCP 工具：{tool}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
