# sylphos/mcp/core.py
"""
Sylphos - MCP bridge minimal prototype

当前版本说明：
- 不真正连接 MCP 服务器，只是演示：
  1）如何接收一条“来自 LLM / 上游”的 MCP 请求
  2）如何根据该请求构造“发往 MCP 服务”的调用参数
  3）给出一个“模拟的 MCP 响应”，方便后续接真服务

后续真正接入时，只需要：
- 替换 `simulate_mcp_service_call()` 为真实的 MCP 客户端调用。
- 删除本文件中标记为 “模拟输入/输出” 的区域。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class MCPRequest:
    """抽象一条来自 LLM / 上游的 MCP 请求（简化 JSON-RPC 请求）."""
    id: str
    method: str          # 例如 "tools.call" / "tools.list"
    params: Dict[str, Any]


@dataclass
class MCPResponse:
    """抽象一条发回给 LLM / 上游的 MCP 响应（简化 JSON-RPC 响应）."""
    id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self.id,
        }
        if self.error is not None:
            payload["error"] = self.error
        else:
            payload["result"] = self.result or {}
        return payload


# =====================================================================
# MCP 调用核心：把“来自 LLM 的请求”转成“对 MCP 服务的调用”
# =====================================================================

def simulate_mcp_service_call(request: MCPRequest) -> MCPResponse:
    """
    当前版本：不真正调用 MCP 服务，只是根据请求返回一个模拟结果。

    将来你可以在这里：
    - 使用 mcp SDK 连接真实 MCP server
    - 把 request.method / request.params 映射为真正的协议调用
    - 根据服务返回的信息构造 MCPResponse
    """
    if request.method == "tools.list":
        fake_tools = [
            {
                "name": "fs.readFile",
                "description": "Read a text file from the local filesystem.",
            },
            {
                "name": "fs.listDir",
                "description": "List directory entries.",
            },
        ]
        return MCPResponse(
            id=request.id,
            result={"tools": fake_tools},
        )

    if request.method == "tools.call":
        tool_name = request.params.get("name")
        tool_args = request.params.get("arguments", {})

        fake_result = {
            "tool": tool_name,
            "echo_arguments": tool_args,
            "note": "当前为模拟结果，请接入真实 MCP 后替换。",
        }
        return MCPResponse(
            id=request.id,
            result=fake_result,
        )

    # 未知方法：返回错误
    return MCPResponse(
        id=request.id,
        error={
            "code": -32601,
            "message": f"Unknown method: {request.method}",
        },
    )


def process_mcp_request(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    上游入口函数：
    - raw: 类似 LLM / API 传入的 JSON-RPC 请求 dict
    - 返回值：可以直接回给 LLM / 上游的 dict 响应
    """
    req = MCPRequest(
        id=str(raw.get("id", "")),
        method=str(raw.get("method", "")),
        params=raw.get("params", {}) or {},
    )

    resp = simulate_mcp_service_call(req)
    return resp.to_dict()


# =====================================================================
# =====================  模 拟 输 入 / 输 出  区  =====================
# =====================================================================
# ⚠️⚠️⚠️
# 这部分代码仅用于本地测试 & 调试。
# 正式接入 MCP 时，你可以：
# - 保留上面的类和函数
# - 删除下面整个 “模拟输入/输出” 区域
# ⚠️⚠️⚠️
# =====================================================================

def _build_mock_llm_request() -> Dict[str, Any]:
    """构造一条“来自 LLM 的 MCP 请求”的模拟数据."""
    return {
        "jsonrpc": "2.0",
        "id": "test-001",
        "method": "tools.call",
        "params": {
            "name": "fs.readFile",
            "arguments": {
                "path": "/etc/hosts",
                "encoding": "utf-8",
            },
        },
    }


def demo_run_once() -> Dict[str, Any]:
    """
    给 runtime 调用的一个小 demo：
    - 构造模拟请求
    - 调用 process_mcp_request
    - 返回响应 dict
    """
    mock_request = _build_mock_llm_request()
    return process_mcp_request(mock_request)


if __name__ == "__main__":
    # 允许单独 python -m sylphos.mcp.core 调试
    resp = demo_run_once()
    print("=== 模拟 MCP -> LLM 输出（response） ===")
    print(resp)
