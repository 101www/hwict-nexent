# -*- coding: utf-8 -*-
"""把 MCP 工具清单【原样】打出来 —— 这就是大模型在运行时看到的全部信息。

为什么要单独有这个脚本：
   当模型「不知道该调哪个工具」或「参数填错」时，第一反应不该是改图谱、
   也不该是改提示词，而是先看这张清单写得够不够清楚。
   工具的 name / description / 参数描述，就是模型与图谱之间唯一的接口说明书。

用法：
    python dump_tools.py http://127.0.0.1:8081/sse
"""
from __future__ import annotations

import json
import sys
import time
from urllib.parse import urljoin, urlparse

from probe_mcp import PROTOCOL_VERSION, SseReader, post_json

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def dump(base_url: str) -> int:
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    sse = SseReader(base_url)
    sse.start()
    for _ in range(50):
        if sse.endpoint_path or sse.error:
            break
        time.sleep(0.1)
    if sse.error:
        print(f"SSE 连接失败: {sse.error}")
        return 1

    msg_url = sse.endpoint_path or base_url
    if not msg_url.startswith("http"):
        msg_url = urljoin(base + "/", msg_url.lstrip("/"))

    post_json(msg_url, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
        "clientInfo": {"name": "dump-tools", "version": "1.0"}}})
    for _ in range(50):
        with sse.lock:
            if sse.responses.get(1):
                break
        time.sleep(0.1)

    post_json(msg_url, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
    post_json(msg_url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    for _ in range(50):
        with sse.lock:
            r = sse.responses.get(2)
        if r:
            break
        time.sleep(0.1)

    if not r:
        print("tools/list 无响应")
        return 1

    tools = r["result"]["tools"]
    print(f"\n{'=' * 70}")
    print(f"共 {len(tools)} 个工具 —— 这是模型在运行时能看到的【全部】信息")
    print(f"{'=' * 70}")
    for t in tools:
        print(f"\n工具名 : {t['name']}")
        print(f"描述   : {t.get('description')}")
        sch = t.get("inputSchema", {})
        req = set(sch.get("required", []))
        print("参数   :")
        for name, spec in sch.get("properties", {}).items():
            mark = "必填" if name in req else "可选"
            print(f"   · {name}  ({spec.get('type')}, {mark})")
            print(f"       {spec.get('description', '（无描述）')}")
    print(f"\n{'=' * 70}")
    print("原始 JSON（模型拿到的就是这段）:")
    print(json.dumps(tools, ensure_ascii=False, indent=2)[:2500])
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8081/sse"
    raise SystemExit(dump(target))
