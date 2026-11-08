"""独立端口启动真实Java，核对历史回放发布前/后/回滚的MCP结果；结束时关闭本脚本的子进程。"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "java-mcp"))
from mcp_client import McpClient


def run(graph_path: Path, release_id: str, expected_paths: int, prefix: str, output: Path):
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    jar = ROOT / "java-mcp/spring-ai-mcp-server/target/spring-ai-mcp-server-0.1.0.jar"
    log_path = output.parent / (prefix + "-java.log")
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(["java", "-jar", str(jar), "--server.address=127.0.0.1",
                                    f"--server.port={port}", f"--kg.graph-path={graph_path}"],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            deadline = time.monotonic() + 40
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"Java启动失败，见{log_path}")
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=0.3):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Java未就绪，见{log_path}")
                    time.sleep(0.2)
            client = McpClient(f"http://127.0.0.1:{port}/sse")
            status = client.call("graph_status",{})
            assert Path(status["source"]).resolve() == graph_path.resolve()
            assert status["meta"]["evolution"]["release_id"] == release_id
            result = client.call("resolve_regimen",{"population":"高血压合并糖尿病患者"})
            paths = [path for item in result["items"] for path in item.get("paths",[])]
            assert len(paths) == expected_paths, (prefix,len(paths))
            if expected_paths:
                assert all(path["hops"] == 2 for path in paths)
                assert result["sufficient"] is False
            references = client.call("check_references",{"keyword":"WS-T872", "limit":10,"offset":0})
            return {"phase":prefix,"endpoint":f"http://127.0.0.1:{port}/sse", "release_id":release_id,
                    "graph_path":str(graph_path), "graph_status":status,
                    "resolve_regimen":{"arguments":{"population":"高血压合并糖尿病患者"},"result":result},
                    "reference_result":references, "path_count":len(paths),"passed":True,
                    "java_stdout":str(log_path)}
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay",type=Path,default=ROOT/"docs/validation/evolution-replay.json")
    parser.add_argument("--out",type=Path,default=ROOT/"docs/validation/evolution-mcp.json")
    args=parser.parse_args()
    replay=json.loads(args.replay.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    store=Path(replay["store"])
    report={"tested_at":datetime.now().astimezone().isoformat(),"kind":"actual_java_sse_mcp_not_llm_answers",
            "review_actor_kind":"automated_test", "phases":[]}
    for phase,rid,count in [("evolution-before",replay["baseline_release"],0),
                            ("evolution-after",replay["published_release"],2),
                            ("evolution-rollback",replay["baseline_release"],0)]:
        result=run(store/"releases"/rid/"graph.json",rid,count,phase,args.out)
        report["phases"].append(result)
        print("PASS",phase,"paths=",result["path_count"],flush=True)
        json_text=json.dumps(report,ensure_ascii=False,indent=2)+"\n"
        args.out.write_text(json_text,encoding="utf-8")
    report["all_passed"]=True
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Saved",args.out)


if __name__=="__main__":
    main()
