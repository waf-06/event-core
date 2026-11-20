#!/usr/bin/env python3
"""build_skill_library — 把三个桌面 App 的 skills 复制成一份 Hermes 可用的技能库。

    python build_skill_library.py [--dest <技能库目录>] [--dry-run]

产物：
  <dest>/<app>/<skill>/...        原样复制的技能目录（保留 SKILL.md 与随附文件）
  <dest>/INDEX.md                 按 App 分组的人读索引（带 description）
  <dest>/catalog.json             机器可读目录：name/app/description/path/tokens
  <dest>/DUPES.md                 同名技能的重复情况（保留首个，其余记录）
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

SOURCES = {
    "qoder": Path.home() / ".qoder-cn" / "skills",
    "workbuddy": Path.home() / ".workbuddy" / "skills",
    "dsh": Path.home() / ".dsh" / "skills",
}
FALLBACK = {
    "workbuddy": Path(os.environ.get("WB_ROOT", str(Path.home() / "Apps" / "WorkBuddy")) + "/resources/app.asar.unpacked/cli/builtin/skills"),
}
DEFAULT_DEST = Path(os.environ.get("MBUS_SKILL_LIB", str(Path.home() / "HermesWork" / "技能库")))


def read_desc(d: Path) -> str:
    for name in ("SKILL.md", "skill.md", "README.md"):
        f = d / name
        if not f.exists():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")[:2000]
        except OSError:
            continue
        m = re.search(r"^description:\s*(.+)$", text, re.M)
        if m:
            return m.group(1).strip().strip('"')
        # 退而求其次：取第一段非标题文字
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                return line[:160]
    return ""


def dir_size(p: Path) -> int:
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            continue
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=str(DEFAULT_DEST))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-mb", type=float, default=0, help="单个 skill 超过该大小则只复制文本文件（0=不限）")
    args = ap.parse_args()

    dest = Path(args.dest)
    catalog: list[dict] = []
    dupes: list[tuple[str, str, str]] = []
    seen: dict[str, str] = {}
    stats: dict[str, dict] = {}

    for app, src in SOURCES.items():
        if not src.exists():
            src = FALLBACK.get(app, src)
        if not src.exists():
            stats[app] = {"found": 0, "copied": 0, "skipped": 0, "bytes": 0}
            continue
        dirs = sorted([d for d in src.iterdir() if d.is_dir() and not d.name.startswith(".")])
        st = {"found": len(dirs), "copied": 0, "skipped": 0, "bytes": 0}
        for d in dirs:
            key = d.name.lower()
            if key in seen:
                dupes.append((d.name, seen[key], app))
                st["skipped"] += 1
                continue
            seen[key] = app
            target = dest / app / d.name
            size = dir_size(d)
            st["bytes"] += size
            st["copied"] += 1
            catalog.append({
                "name": d.name,
                "app": app,
                "description": read_desc(d),
                "path": str(target),
                "source": str(d),
                "bytes": size,
            })
            if args.dry_run:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(d, target, ignore=shutil.ignore_patterns("__pycache__", ".git", "node_modules"))
        stats[app] = st

    if not args.dry_run:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "catalog.json").write_text(
            json.dumps({"version": 1, "count": len(catalog), "skills": catalog}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

        lines = ["# 技能库索引", "",
                 f"来源：Qoder CN / WorkBuddy / DeepSeek Harness 三套 App 的 skills，按 App 分组复制。",
                 f"共 {len(catalog)} 个技能；`catalog.json` 是机器可读版（name/app/description/path）。", ""]
        for app in SOURCES:
            items = [c for c in catalog if c["app"] == app]
            lines.append(f"## {app}（{len(items)}）")
            lines.append("")
            for c in items:
                desc = c["description"] or "（无 description）"
                lines.append(f"- **{c['name']}** — {desc}")
            lines.append("")
        (dest / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")

        if dupes:
            (dest / "DUPES.md").write_text(
                "# 同名技能\n\n同名只保留首个（按 qoder → workbuddy → dsh 顺序），其余记录在此：\n\n"
                + "\n".join(f"- `{n}`：保留 {kept}，重复来自 {other}" for n, kept, other in dupes) + "\n",
                encoding="utf-8")

    total_mb = sum(s["bytes"] for s in stats.values()) / 1024 / 1024
    for app, s in stats.items():
        print(f"{app:10s} 找到 {s['found']:3d} · 复制 {s['copied']:3d} · 跳过重复 {s['skipped']:3d} · {s['bytes']/1024/1024:6.1f} MB")
    print(f"合计 {len(catalog)} 个技能 / {total_mb:.1f} MB → {dest}")
    print("dry-run，未写盘" if args.dry_run else "已写入 INDEX.md / catalog.json" + (" / DUPES.md" if dupes else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
