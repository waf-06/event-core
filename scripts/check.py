#!/usr/bin/env python3
"""项目自检：把「复盘出来的规则」变成可执行检查。

    python scripts/check.py            # 常规自检（本地开发）
    python scripts/check.py --public   # 发布前自检（多扫敏感信息 + 本机路径）

只依赖标准库；不调用 git（Windows 上 Python 起不了部分程序），直接读目录。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
import pathlib
import re
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "shots", "rooms", "cua"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".exe", ".zip", ".pyc", ".woff", ".woff2"}

SECRET_PATTERNS = {
    "密钥(sk-/gh)": re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "私钥块": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
    "赋值凭据": re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret|password|passwd)\s*[:=]\s*['\"][^'\"\n]{12,}['\"]"),
    "邮箱": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"),
    "手机号": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "用户目录": re.compile(r"[C-Z]:[\\/]{1,2}[Uu]sers[\\/]+[\w\-.]+"),
    "设备名": re.compile(r"(?i)DESKTOP-[A-Z0-9]{6,}"),
    "长随机串": re.compile(r"\b[A-Za-z0-9]{32,}\b"),
}

OK, BAD = "✅", "❌"
problems: list[str] = []


def iter_files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in SKIP_EXT:
            continue
        if p.name.endswith((".log", ".bak")) or p.name.startswith(".last_room"):
            continue
        yield p


def scan(public: bool) -> None:
    hits: dict[str, list[str]] = {}
    count = 0
    for p in iter_files():
        count += 1
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, rx in SECRET_PATTERNS.items():
            for m in rx.finditer(txt):
                line = txt[:m.start()].count("\n") + 1
                hits.setdefault(name, []).append(f"{p.relative_to(ROOT)}:{line}  {m.group(0)[:60]}")
    if hits:
        for k, v in hits.items():
            print(f"{BAD} {k}: {len(v)} 处")
            for h in v[:5]:
                print("     ", h)
        problems.append("敏感信息")
    else:
        print(f"{OK} 敏感信息   {count} 个文件，无命中")

    if public:
        local = []
        for p in iter_files():
            if p.suffix not in (".py", ".md", ".json", ".html", ".js", ".sh", ".cmd", ".ts"):
                continue
            txt = p.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"[A-Z]:[\\/]+[\w\u4e00-\u9fff\- ]{3,}", txt):
                if "Users/19420" in m.group(0) or "19420" in m.group(0):
                    local.append(f"{p.relative_to(ROOT)}: {m.group(0)[:60]}")
        if local:
            print(f"{BAD} 本机路径: {len(local)} 处")
            for x in local[:5]:
                print("     ", x)
            problems.append("本机路径")
        else:
            print(f"{OK} 本机路径   无绝对路径")


class _GridProbe(HTMLParser):
    """找 grid 容器，比较「直接子元素数」和「grid-template-rows 的轨道数」。

    R1 就是这么踩的：往 .app 里加了第 5 块，行定义还是 4 条 → 隐式行把底部通栏顶出屏幕，
    按钮看着在、其实点不到。
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # 每层是否是该容器
        self.targets = []        # [(class, children)]
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        is_target = "app" in cls.split()
        if self.stack and self.stack[-1] is not None:
            self.stack[-1] += 1
        if tag not in ("br", "img", "input", "meta", "link", "hr"):
            self.stack.append(0 if is_target else None)
            if is_target:
                self.targets.append([cls, self.stack[-1]])
        else:
            if self.stack and self.stack[-1] is not None:
                self.stack[-1] += 1

    def handle_endtag(self, tag):
        if tag in ("br", "img", "input", "meta", "link", "hr"):
            return
        if self.stack:
            n = self.stack.pop()
            if n is not None and self.targets:
                self.targets[-1][1] = n

    def handle_data(self, data):
        pass


def check_ui_grid() -> None:
    """静态检查：grid 行数 vs 子块数。"""
    bad = []
    for p in iter_files():
        if p.suffix not in (".html",):
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        tracks = None
        for m in __import__("re").finditer(r"\.app\s*\{[^}]*grid-template-rows\s*:\s*([^;}]+)", txt):
            tracks = m.group(1)
        if not tracks:
            continue
        n_tracks = len([t for t in tracks.split() if t.strip()])
        probe = _GridProbe()
        try:
            probe.feed(txt)
        except Exception:  # noqa: BLE001
            continue
        if probe.targets:
            n_children = probe.targets[0][1]
            if n_children > n_tracks:
                bad.append(f"{p.name}: 子块 {n_children} 个 > 行定义 {n_tracks} 条")
    if bad:
        print(f"{BAD} 布局行数   {len(bad)} 处（会生成隐式行，底部可能被顶出屏幕）")
        for b in bad:
            print("     ", b)
        problems.append("布局行数")
    else:
        print(f"{OK} 布局行数   grid 行定义与子块数一致")



def check_inline_js() -> None:
    """每个 HTML 里的内联脚本都过一遍 node --check。

    为什么：页面 HTTP 200、DOM 结构正确，也可能因为一行写坏的正则整页白屏。
    这类故障肉眼看不出来，只能靠语法检查兜住。
    """
    if not shutil.which("node"):
        print(f"{OK} 内联脚本   node 不可用，跳过")
        return
    bad = []
    for f in sorted(ROOT.glob("*.html")):
        text = f.read_text(encoding="utf-8", errors="replace")
        for i, m in enumerate(re.finditer(r"<script>(.*?)</script>", text, re.S)):
            js = m.group(1)
            if len(js.strip()) < 50:
                continue
            tmp = pathlib.Path(tempfile.gettempdir()) / f"_chk_{f.stem}_{i}.js"
            tmp.write_text(js, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(tmp)], capture_output=True, text=True)
            tmp.unlink(missing_ok=True)
            if r.returncode:
                err = [ln.strip() for ln in r.stderr.splitlines() if "SyntaxError" in ln]
                bad.append(f"{f.name} 脚本{i}: {(err[0] if err else '语法错误')[:90]}")
    if bad:
        print(f"{BAD} 内联脚本   {len(bad)} 处语法错误（页面会白屏）")
        for b in bad[:5]:
            print("     ", b)
        problems.append("内联脚本")
    else:
        print(f"{OK} 内联脚本   全部可解析")


def probe() -> None:
    for name, url in (("engine", "http://127.0.0.1:8765/api/agents"),):
        try:
            with urllib.request.urlopen(url, timeout=4) as r:
                ok = r.status == 200
        except (urllib.error.URLError, OSError):
            ok = False
        print(f"{OK if ok else BAD} {name:8}   {'200' if ok else '没有响应'}")
        if not ok:
            problems.append(name)


def api_checks() -> None:
    def get(path):
        with urllib.request.urlopen("http://127.0.0.1:8765" + path, timeout=6) as r:
            return json.loads(r.read())

    try:
        agents = get("/api/agents").get("agents", [])
        skills = get("/api/skills?limit=200").get("skills", [])
        rooms = get("/api/rooms").get("rooms", [])
        print(f"{OK} 接口       agents {len(agents)} · skills {len(skills)} · rooms {len(rooms)}")
        if not agents:
            problems.append("/api/agents 为空")
        states = {r.get("status") for r in rooms}
        known = {"running", "synthesizing", "awaiting", "done", "interrupted"}
        bad = states - known
        if bad:
            print(f"{BAD} 状态机     出现未知状态 {bad}")
            problems.append("未知房间状态")
        else:
            print(f"{OK} 状态机     {' / '.join(sorted(s for s in states if s)) or '暂无'}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        print(f"{BAD} 接口       不可用：{e}")
        problems.append("接口")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public", action="store_true", help="发布前模式：额外扫本机路径")
    args = ap.parse_args()

    scan(args.public)
    check_ui_grid()
    check_inline_js()
    probe()
    api_checks()

    print()
    if problems:
        print(f"{BAD} 有 {len(problems)} 类问题：{', '.join(problems)}")
        return 1
    print(f"{OK} 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
