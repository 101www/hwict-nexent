# -*- coding: utf-8 -*-
"""MCP 客户端探针：独立验证 Java 侧 MCP 服务是否真的按协议响应。

做完整的三步握手：
  1. GET  <base>/sse  → 拿到 session 的 messages 端点
  2. POST initialize  → 协议版本与 capabilities 协商
  3. POST tools/list  → 工具发现（只证明该客户端能连接，不代表远程 Nexent 的网络也可达）

同时兼容 Streamable HTTP 单一端点（POST <base>/mcp 带 JSON 响应）。

用法：
    python probe_mcp.py http://127.0.0.1:8081/sse
    python probe_mcp.py http://127.0.0.1:8082/mcp
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

# Windows 控制台默认 GBK，直接打印 ✓/✅ 会抛 UnicodeEncodeError，这里统一切到 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

PROTOCOL_VERSION = "2024-11-05"


class SseReader(threading.Thread):
    """后台读 SSE 流，把收到的 JSON-RPC 响应按 id 存起来。"""

    def __init__(self, url: str) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.endpoint_path: str | None = None
        self.responses: dict[object, dict] = {}
        self.raw_lines: list[str] = []
        self.lock = threading.Lock()
        self.error: str | None = None

    def run(self) -> None:
        try:
            req = urllib.request.Request(
                self.url, headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                cur_event = None
                for raw in resp:
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if not line:
                        cur_event = None
                        continue
                    self.raw_lines.append(line)
                    if line.startswith("event:"):
                        cur_event = line[6:].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if cur_event == "endpoint" or data.startswith("/"):
                        self.endpoint_path = data
                        continue
                    if data.startswith("http"):
                        self.endpoint_path = data
                        continue
                    try:
                        msg = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(msg, dict) and "id" in msg:
                        with self.lock:
                            self.responses[msg["id"]] = msg
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"


def post_json(url: str, payload: dict, session_id: str | None = None) -> dict | None:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.status
            sid = resp.headers.get("Mcp-Session-Id")
            text = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code} {e.reason}: {e.read().decode('utf-8', 'replace')[:300]}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"    POST 失败: {type(exc).__name__}: {exc}")
        return None

    print(f"    HTTP {status}" + (f"  Mcp-Session-Id={sid}" if sid else ""))
    if not text.strip():
        return None
    # Streamable HTTP 可能直接返回 JSON，也可能返回 SSE 格式
    if text.lstrip().startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    for line in text.splitlines():
        if line.startswith("data:"):
            try:
                return json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
    return None


def probe(url: str) -> bool:
    print(f"\n{'=' * 70}\n探测: {url}\n{'=' * 70}")
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    sse: SseReader | None = None
    msg_url = url
    session_id: str | None = None

    if url.rstrip("/").endswith("/sse"):
        sse = SseReader(url)
        sse.start()
        for _ in range(50):  # 最多等 5s 拿 messages 端点
            if sse.endpoint_path or sse.error:
                break
            time.sleep(0.1)
        if sse.error:
            print(f"  SSE 连接失败: {sse.error}")
            return False
        if sse.endpoint_path:
            path = sse.endpoint_path
            msg_url = path if path.startswith("http") else urljoin(base + "/", path.lstrip("/"))
        else:
            print("  未取到 messages 端点，回退为直接 POST 原地址")
        print(f"  messages 端点: {msg_url}")
    else:
        print("  传输: Streamable HTTP（单一端点）")

    print("\n[1/3] initialize")
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "probe-client", "version": "1.0"},
        },
    }
    r1 = post_json(msg_url, init, session_id)
    if r1 is None and sse:
        for _ in range(30):
            with sse.lock:
                r1 = sse.responses.get(1)
            if r1:
                break
            time.sleep(0.1)
    if not r1:
        print("  ✗ initialize 无响应")
        return False

    result = r1.get("result", {})
    info = result.get("serverInfo", {})
    caps = result.get("capabilities", {})
    print(f"  ✓ serverInfo: {info.get('name')} v{info.get('version')}")
    print(f"  ✓ protocolVersion: {result.get('protocolVersion')}")
    print(f"  ✓ capabilities: {list(caps.keys())}")

    # 通知 initialized（无响应）
    post_json(
        msg_url,
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        session_id,
    )

    print("\n[2/3] tools/list")
    r2 = post_json(msg_url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_id)
    if r2 is None and sse:
        for _ in range(50):
            with sse.lock:
                r2 = sse.responses.get(2)
            if r2:
                break
            time.sleep(0.1)
    if not r2:
        print("  ✗ tools/list 无响应")
        return False

    tools = r2.get("result", {}).get("tools", [])
    print(f"  ✓ 发现 {len(tools)} 个工具：")
    for t in tools:
        schema = t.get("inputSchema", {})
        params = list(schema.get("properties", {}).keys())
        required = schema.get("required", [])
        print(f"      - {t['name']}")
        print(f"          描述: {(t.get('description') or '')[:60]}...")
        print(f"          参数: {params}  必填: {required}")

    print("\n[3/3] tools/call 实测（调用 find_entities）")
    if any(t["name"] == "find_entities" for t in tools):
        call = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "find_entities", "arguments": {"keyword": "血压达标患者", "limit": 3}},
        }
        r3 = post_json(msg_url, call, session_id)
        if r3 is None and sse:
            for _ in range(50):
                with sse.lock:
                    r3 = sse.responses.get(3)
                if r3:
                    break
                time.sleep(0.1)
        if r3:
            content = r3.get("result", {}).get("content", [])
            for c in content:
                txt = c.get("text", "")
                print("  ✓ 返回内容（截断 400 字）：")
                print("      " + txt[:400].replace("\n", "\n      "))
        else:
            print("  ✗ tools/call 无响应")
    else:
        print("  （该服务未提供 find_entities，跳过）")

    print(f"\n结论: {'✅ 已发现 MCP 工具；真实数据验收请运行 test_real_graph_mcp.py' if tools else '❌ 未发现任何工具'}")
    return bool(tools)


if __name__ == "__main__":
    targets = sys.argv[1:] or ["http://127.0.0.1:8081/sse", "http://127.0.0.1:8082/mcp"]
    ok = all(probe(t) for t in targets)
    sys.exit(0 if ok else 1)
