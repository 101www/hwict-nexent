"""读取真实MCP响应并与生产仓库指针对比；不调用模型、不修改Nexent。"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "java-mcp")]
from pipeline.evolution import EvolutionStore
from mcp_client import McpClient

def check(store=None, url="http://192.168.100.1:8081/sse"):
    store = store or EvolutionStore(ROOT / "data/evolution/production")
    expected = store.state()["current"]
    client = McpClient(url)
    status = client.call("graph_status", {})
    version = status.get("knowledge_version", {})
    return {"checked_at":datetime.now().astimezone().isoformat(), "endpoint":url,
            "expected_release":expected, "actual_release":version.get("release_id"),
            "matches_current_published_version":version.get("release_id")==expected,
            "document_count":len(status.get("meta",{}).get("documents",[])),
            "verification":version.get("verification"), "nodes":status.get("nodes"),
            "edges":status.get("edges"), "graph_status":status,
            "limits":"本机直接调用真实MCP；并非Nexent页面发起的调用，不核验临床结论"}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url",default="http://192.168.100.1:8081/sse")
    args=parser.parse_args()
    try:
        result=check(url=args.url)
        summary={k:v for k,v in result.items() if k!="graph_status"}
        print(json.dumps(summary,ensure_ascii=False,indent=2))
        return 0 if result["matches_current_published_version"] else 1
    except (OSError,RuntimeError,ValueError,TimeoutError) as exc:
        print("连接检查失败，请先保持《启动正式图谱MCP.cmd》运行：",exc,file=sys.stderr)
        return 1

if __name__=="__main__": raise SystemExit(main())
