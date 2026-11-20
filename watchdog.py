#!/usr/bin/env python3
"""watchdog — 守住调度引擎 8765（Qoder 常驻池已并入引擎，不再单独占端口）。

每 60 秒探一次，挂了就拉起来。日志写 watchdog.log（超过 1MB 自动截断）。

    python watchdog.py            # 前台常驻
    python watchdog.py --once     # 只查一次（给计划任务用）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "watchdog.log"
LOCK = ROOT / ".watchdog.lock"

SERVICES = [
    {"name": "engine", "url": "http://127.0.0.1:8765/api/agents", "script": "ui.py", "warm": []},
]


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        if LOG.exists() and LOG.stat().st_size > 1_000_000:
            LOG.write_text("", encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def alive(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def start(svc: dict) -> None:
    py = sys.executable
    script = ROOT / svc["script"]
    if not script.exists():
        log(f"{svc['name']}: 脚本不存在 {script}")
        return
    creation = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        p = subprocess.Popen([py, str(script)], cwd=str(ROOT), close_fds=True,
                             creationflags=creation if os.name == "nt" else 0,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"{svc['name']}: 已拉起 pid={p.pid}")
    except OSError as e:
        log(f"{svc['name']}: 启动失败 {e}")


def check_all() -> None:
    for svc in SERVICES:
        if alive(svc["url"]):
            continue
        log(f"{svc['name']}: 没有响应，重启中…")
        start(svc)
        for _ in range(20):
            time.sleep(1.5)
            if alive(svc["url"]):
                log(f"{svc['name']}: 恢复")
                break
        else:
            log(f"{svc['name']}: 仍无响应（看 {svc['script']} 自己的日志）")


def main() -> int:
    once = "--once" in sys.argv
    if once:
        check_all()
        return 0

    # 单实例锁
    if LOCK.exists():
        try:
            pid = int(LOCK.read_text().strip() or 0)
            if pid and _pid_alive(pid):
                print(f"watchdog 已在运行 pid={pid}")
                return 0
        except (ValueError, OSError):
            pass
    LOCK.write_text(str(os.getpid()), encoding="utf-8")

    log("watchdog 启动 · 60s 间隔")
    try:
        while True:
            check_all()
            time.sleep(60)
    except KeyboardInterrupt:
        log("watchdog 退出")
    finally:
        LOCK.unlink(missing_ok=True)
    return 0


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
