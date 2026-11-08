"""本项目 SSE MCP 自测客户端，只使用 Python 标准库，不调用大模型。"""
from __future__ import annotations

import json
import time
from urllib.parse import urljoin

from probe_mcp import PROTOCOL_VERSION, SseReader, post_json


class McpClient:
    def __init__(self, url: str = "http://127.0.0.1:8081/sse") -> None:
        self.reader = SseReader(url)
        self.reader.start()
        deadline = time.monotonic() + 8
        while not self.reader.endpoint_path:
            if self.reader.error:
                raise RuntimeError(self.reader.error)
            if time.monotonic() >= deadline:
                raise TimeoutError("未收到 SSE 消息端点，请确认 Java MCP 已启动。")
            time.sleep(0.05)
        self.endpoint = urljoin(url, self.reader.endpoint_path)
        self.sequence = 0
        self.server = self.rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "real-graph-check", "version": "0.2.0"},
        })
        post_json(self.endpoint, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def rpc(self, method: str, params: dict) -> dict:
        self.sequence += 1
        ident = self.sequence
        response = post_json(self.endpoint, {
            "jsonrpc": "2.0", "id": ident, "method": method, "params": params,
        })
        deadline = time.monotonic() + 10
        while response is None:
            with self.reader.lock:
                response = self.reader.responses.pop(ident, None)
            if response is not None:
                break
            if self.reader.error:
                raise RuntimeError(self.reader.error)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"MCP {method} 未响应")
            time.sleep(0.02)
        if "error" in response:
            raise RuntimeError(f"MCP {method}: {response['error']}")
        if "result" not in response:
            raise RuntimeError(f"MCP {method} 未返回 result")
        return response["result"]

    def list_tools(self) -> list[dict]:
        return self.rpc("tools/list", {}).get("tools", [])

    def call(self, name: str, arguments: dict) -> dict:
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(f"工具 {name} 返回错误: {result.get('content')}")
        if isinstance(result.get("structuredContent"), dict):
            return result["structuredContent"]
        texts = [c["text"] for c in result.get("content", []) if c.get("type") == "text"]
        if len(texts) != 1:
            raise RuntimeError(f"工具 {name} 返回了无法解析的内容")
        return json.loads(texts[0])
