#!/usr/bin/env python3
"""qoder-mcp — 把 Qoder CLI CN 包装成 MCP 工具，供 Hermes 直接调用。

不依赖 mcp SDK：自己实现 stdio JSON-RPC（MCP 的 stdio 传输是「一行一个 JSON」）。

工具：
  ask_qoder(prompt, model?, cwd?, max_turns?, allowed_tools?, no_tools?, resume?, timeout?)
  qoder_models()
  qoder_status()
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CANDIDATES = [
    Path.home() / ".qoder-cn/bin/qoderclicn/qoderclicn.exe",
    Path.home() / ".qoder-cn/bin/qoderclicn/qoderclicn",
]
CLI = next((str(p) for p in CANDIDATES if p.exists()), shutil.which("qoderclicn") or "")
def _local_cfg() -> dict:
    try:
        return json.loads((Path(__file__).resolve().parent / "local.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


WORKSPACE = os.environ.get("QODER_WORKSPACE") or _local_cfg().get("workspace") or str(Path.home() / "HermesWork")
WORKER = "http://127.0.0.1:8765"

TOOLS = [
    {
        "name": "ask_qoder",
        "description": (
            "把一个任务交给 Qoder CN（官方 CLI/Agent）执行，消耗你 Qoder 账号的 Credits。"
            "它会带自己的系统提示词和工具循环，适合整段任务：写代码、读仓库、重构、调研。"
            "纯问答建议 max_turns=1 且 no_tools=true，否则会很慢且更贵。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "要 Qoder 做的事"},
                "model": {"type": "string", "description": "模型名，如 Qwen3.8-Flash / DeepSeek-Flash / Kimi-K3.1-Pro / Auto", "default": "Auto"},
                "cwd": {"type": "string", "description": "工作目录，默认取 $QODER_WORKSPACE / local.json 里的 workspace"},
                "max_turns": {"type": "integer", "description": "最大 agent 轮数，默认 1", "default": 1},
                "allowed_tools": {"type": "string", "description": "允许的工具，如 Read,Grep"},
                "no_tools": {"type": "boolean", "description": "禁用所有工具（纯模型问答）", "default": False},
                "resume": {"type": "string", "description": "续接已有会话的 session_id"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 240", "default": 240},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "qoder_models",
        "description": "列出当前 Qoder 账号可用的模型（含 BYOK 自定义模型）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "qoder_status",
        "description": "查看 Qoder CLI 版本与登录状态。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def run_cli(args: list[str], timeout: int = 240) -> tuple[int, str, str]:
    if not CLI:
        return 127, "", "找不到 qoderclicn：先跑 install.ps1 安装，并确认 ~/.qoder-cn/bin/qoderclicn 存在"
    try:
        p = subprocess.run([CLI, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           cwd=WORKSPACE if Path(WORKSPACE).exists() else None)
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"超时（{timeout}s）"
    except OSError as e:
        return 126, "", f"启动失败：{e}"


def ask_via_worker(prompt: str, model: str, timeout: int) -> dict | None:
    """常驻 worker 优先（3 秒级）；没起就返回 None 走冷启动。"""
    import urllib.request
    import urllib.error
    body = json.dumps({"prompt": prompt, "model": model, "timeout": timeout},
                      ensure_ascii=False).encode()
    req = urllib.request.Request(WORKER + "/api/qoder/ask", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout + 30) as resp:
            d = json.loads(resp.read())
        return d if d.get("ok") else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def ask_qoder(a: dict) -> dict:
    prompt = (a.get("prompt") or "").strip()
    if not prompt:
        return {"error": "prompt 不能为空"}
    model = a.get("model") or "Auto"
    max_turns = int(a.get("max_turns") or 1)
    timeout = int(a.get("timeout") or 240)
    cwd = a.get("cwd") or WORKSPACE

    args = ["-p", prompt, "-o", "json", "--max-turns", str(max_turns), "-m", model,
            "--permission-mode", "dont_ask"]
    if cwd:
        args += ["-w", cwd]
    if a.get("no_tools"):
        args += ["--tools", ""]
    if a.get("allowed_tools"):
        args += ["--allowed-tools", a["allowed_tools"]]
    if a.get("resume"):
        args += ["--resume", a["resume"]]

    if not a.get("resume") and not a.get("allowed_tools") and not a.get("cwd"):
        warm = ask_via_worker(prompt, model, timeout)
        if warm:
            return {"ok": True, "text": warm.get("text", ""), "model": model,
                    "credits": warm.get("credits", 0), "turns": 1,
                    "session_id": warm.get("session_id", ""),
                    "duration_ms": warm.get("duration_ms"),
                    "tokens": {"in": 0, "out": 0, "cache": 0},
                    "via": "worker"}

    t0 = time.time()
    code, out, err = run_cli(args, timeout)

    payload = {}
    for line in reversed([l for l in out.splitlines() if l.strip().startswith("{")]):
        try:
            payload = json.loads(line)
            break
        except json.JSONDecodeError:
            continue

    if not payload:
        return {"ok": False, "exit": code, "error": (err or out or "没有输出").strip()[:800],
                "elapsed_s": round(time.time() - t0, 1)}

    usage = payload.get("modelUsage") or {}
    credits = payload.get("total_credits") or sum((v or {}).get("credits", 0) for v in usage.values())
    tu = payload.get("usage") or {}
    return {
        "ok": not payload.get("is_error", False),
        "text": payload.get("result", ""),
        "model": model,
        "credits": round(float(credits or 0), 4),
        "turns": payload.get("num_turns"),
        "session_id": payload.get("session_id", ""),
        "duration_ms": payload.get("duration_ms", int((time.time() - t0) * 1000)),
        "tokens": {"in": tu.get("input_tokens", 0), "out": tu.get("output_tokens", 0),
                   "cache": tu.get("cache_read_input_tokens", 0)},
        "context_usage": tu.get("context_usage_ratio"),
        "denials": payload.get("permission_denials") or [],
    }


def call_tool(name: str, args: dict) -> dict:
    if name == "ask_qoder":
        return ask_qoder(args)
    if name == "qoder_models":
        code, out, err = run_cli(["--list-models"], 90)
        models = [l.strip() for l in out.splitlines()[1:] if l.strip()]
        return {"ok": code == 0, "models": models, "error": err[:300] if code else ""}
    if name == "qoder_status":
        code, out, err = run_cli(["status"], 60)
        info = {}
        for line in out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
        return {"ok": code == 0, "via": "cli", **info, "error": err[:300] if code else ""}
    return {"error": f"未知工具 {name}"}


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(req: dict) -> None:
    method = req.get("method", "")
    rid = req.get("id")

    if method == "initialize":
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "qoder-mcp", "version": "1.0.0"},
        }})
        return

    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return

    if method == "ping":
        send({"jsonrpc": "2.0", "id": rid, "result": {}})
        return

    if method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        return

    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            result = call_tool(name, args)
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            "structuredContent": result,
            "isError": not result.get("ok", True),
        }})
        return

    if rid is not None:
        send({"jsonrpc": "2.0", "id": rid,
              "error": {"code": -32601, "message": f"method not found: {method}"}})


def main() -> int:
    if "--selftest" in sys.argv:
        print(json.dumps({"cli": CLI, "models": call_tool("qoder_models", {})["models"][:5]},
                         ensure_ascii=False, indent=2))
        return 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle(req)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
