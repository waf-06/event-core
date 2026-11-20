#!/usr/bin/env python3
"""mbus - Hermes model bus.

One router for: local Ollama models, hosted OpenAI-compatible APIs, and desktop
agent apps (WorkBuddy/CodeBuddy, Qoder, DeepSeek Harness, Doubao).

Commands
  mbus doctor                      health of every backend
  mbus models                      list backends + app config pointers
  mbus models set <backend> <model> [--base-url U] [--label L]
  mbus models use <tier> <backend>  change routing tier
  mbus run "prompt" [--backend B|--tier T] [--system S] [--json]
  mbus classify "task"             show routing decision + reason
  mbus dispatch "task" [--split N] [--no-synth] [--dry-run] [--json]
  mbus sync                        render app configs (WorkBuddy models.json)
  mbus handoff --app <app> "task"  push a task to a GUI app (clipboard + focus)
  mbus usage [--days 7] [--by model|backend|day] [--html] [--json]
  mbus ingest                      pull real usage from DeepSeek Harness ledger
  mbus balance                     DeepSeek account balance

Zero third-party dependencies (stdlib only / Python 3.10+).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import random
import re
import string
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "models.json"
HERMES_ENV = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / ".env"
LEDGER_LOCK = threading.Lock()


# ---------------------------------------------------------------- config / io
def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, CONFIG_PATH)


def load_env() -> dict:
    """Hermes .env plus process env. Process env wins."""
    env: dict[str, str] = {}
    for p in (Path.home() / ".hermes" / ".env", HERMES_ENV):
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
    env.update({k: v for k, v in os.environ.items() if v})
    return env


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def task_id() -> str:
    return "t-" + dt.datetime.now().strftime("%y%m%d%H%M%S") + "-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=4))


# ---------------------------------------------------------------- ledger
def append_ledger(records: list[dict]) -> None:
    if not records:
        return
    cfg = load_config()
    path = Path(cfg["paths"]["ledger"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_ledger() -> list[dict]:
    path = Path(load_config()["paths"]["ledger"])
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def is_peak(ts: dt.datetime | None = None) -> bool:
    """DeepSeek peak: 01:00-04:00 and 06:00-10:00 UTC, Mon-Fri."""
    t = (ts or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    if t.weekday() >= 5:
        return False
    return (1 <= t.hour < 4) or (6 <= t.hour < 10)


def budget_window(period: str) -> dt.datetime | None:
    t = now()
    if period == "day":
        return t.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


def budget_state(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    b = cfg.get("budget") or {}
    cap = float(b.get("cny", 0) or 0)
    period = b.get("period", "month")
    start = budget_window(period)
    spent = 0.0
    for r in read_ledger():
        if start is None:
            spent += r.get("cost_cny", 0)
            continue
        try:
            if dt.datetime.fromisoformat(r["ts"]) >= start:
                spent += r.get("cost_cny", 0)
        except Exception:  # noqa: BLE001
            continue
    return {"cap": cap, "period": period, "spent": spent, "remaining": max(0.0, cap - spent),
            "pct": (spent / cap * 100) if cap else 0.0, "hard": bool(b.get("hard", True))}


def check_budget(cfg: dict, force: bool = False) -> None:
    st = budget_state(cfg)
    if not st["cap"] or not st["hard"] or force:
        return
    if st["spent"] >= st["cap"]:
        label = {"day": "今日", "month": "本月"}.get(st["period"], "累计")
        raise RuntimeError(
            f"预算已用尽：{label}已花 ¥{st['spent']:.2f} / 上限 ¥{st['cap']:.2f}。"
            f"本地模型仍然免费可用（--tier simple/medium），或加 --force 强制越过。")


def cost_cny(backend: dict, usage: dict, cfg: dict) -> float:
    p = backend.get("price_usd") or {}
    if not p:
        return 0.0
    mult = backend.get("peak_multiplier", 1.0) if is_peak() else 1.0
    pin = float(p.get("in", 0.0))
    pcache = float(p.get("cache", pin))
    pout = float(p.get("out", 0.0))
    usd = (usage.get("in", 0) * pin + usage.get("cache", 0) * pcache + usage.get("out", 0) * pout) / 1_000_000
    return usd * mult * float(cfg.get("usd_cny", 7.15))


# ---------------------------------------------------------------- backends
def http_json(url: str, payload: dict | None = None, headers: dict | None = None, timeout: int = 300) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def call_ollama(backend: dict, messages: list[dict], max_tokens: int | None) -> dict:
    url = backend["base_url"].rstrip("/") + "/api/chat"
    payload = {
        "model": backend["model"],
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": backend.get("num_ctx", 65536), "temperature": backend.get("temperature", 0.3)},
    }
    if backend.get("think") is False:
        payload["think"] = False
    limit = max_tokens or backend.get("max_tokens")
    if limit:
        payload["options"]["num_predict"] = limit
    raw = http_json(url, payload, timeout=backend.get("timeout", 240))
    text = (raw.get("message") or {}).get("content", "")
    usage = {"in": raw.get("prompt_eval_count", 0), "out": raw.get("eval_count", 0), "cache": 0}
    return {"text": text, "usage": usage, "raw": raw}


def call_openai(backend: dict, messages: list[dict], max_tokens: int | None, env: dict) -> dict:
    key_name = backend.get("key_env", "")
    key = env.get(key_name, "")
    if not key:
        raise RuntimeError(f"缺少 API key：{key_name} 未在 .env / 环境变量中找到")
    url = backend["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": backend["model"],
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens or backend.get("max_tokens", 4096),
    }
    if backend.get("thinking_effort"):
        payload["thinking"] = {"type": "enabled", "effort": backend["thinking_effort"]}
    elif backend.get("thinking") is False:
        payload["thinking"] = {"type": "disabled"}
    raw = http_json(url, payload, {"Authorization": f"Bearer {key}"}, timeout=backend.get("timeout", 180))
    choice = (raw.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    if not text and msg.get("reasoning_content"):
        text = "（思考被 max_tokens 截断，没有产出正文）"
    u = raw.get("usage") or {}
    cache_hit = u.get("prompt_cache_hit_tokens", 0)
    usage = {
        "in": max(0, u.get("prompt_tokens", 0) - cache_hit),
        "out": u.get("completion_tokens", 0),
        "cache": cache_hit,
        "total_in": u.get("prompt_tokens", 0),
        "reasoning": (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
    }
    return {"text": text, "usage": usage, "raw": raw}


def run_backend(name: str, prompt: str, system: str | None = None, max_tokens: int | None = None,
                tid: str | None = None, step: int = 0, quiet: bool = False, force: bool = False) -> dict:
    cfg = load_config()
    backend = cfg["backends"][name]
    if backend.get("kind") == "app":
        raise RuntimeError(f"backend '{name}' 是桌面 App，请用 `mbus handoff --app {backend.get('app')}` 交付任务")
    if (backend.get("price_usd") or {}).get("in", 0) or (backend.get("price_usd") or {}).get("out", 0):
        check_budget(cfg, force)
    env = load_env()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    t0 = time.time()
    err = None
    try:
        if backend["kind"] == "ollama":
            res = call_ollama(backend, messages, max_tokens)
        else:
            res = call_openai(backend, messages, max_tokens, env)
    except Exception as e:  # noqa: BLE001
        err = str(e)
        res = {"text": "", "usage": {"in": 0, "out": 0, "cache": 0}}
    latency = int((time.time() - t0) * 1000)
    rec = {
        "ts": now().isoformat(timespec="seconds"),
        "task_id": tid or task_id(),
        "step": step,
        "backend": name,
        "model": backend.get("model", name),
        "provider": backend.get("base_url", ""),
        "kind": backend["kind"],
        "in": res["usage"].get("in", 0),
        "cache": res["usage"].get("cache", 0),
        "out": res["usage"].get("out", 0),
        "cost_cny": round(cost_cny(backend, res["usage"], cfg), 6),
        "latency_ms": latency,
        "ok": err is None,
        "error": err,
        "source": "api" if err is None else "api-error",
    }
    append_ledger([rec])
    if not quiet:
        tok = f"{rec['in']}+{rec['cache']}c→{rec['out']} tok" if rec["cache"] else f"{rec['in']}→{rec['out']} tok"
        tail = f"¥{rec['cost_cny']:.4f}" if rec["cost_cny"] else "免费"
        print(f"[mbus] {name} · {backend.get('model', '')} · {tok} · {tail} · {latency} ms", file=sys.stderr)
    if err:
        raise RuntimeError(err)
    return res["text"]


# ---------------------------------------------------------------- routing
def classify(task: str, cfg: dict) -> tuple[str, list[str]]:
    r = cfg["routing"]
    n = len(task)
    reasons = [f"长度 {n} 字符"]
    score = 0
    if n > r["medium_max_chars"]:
        score += 2
        reasons.append("超过 medium 长度阈值")
    elif n > r["simple_max_chars"]:
        score += 1
        reasons.append("超过 simple 长度阈值")
    low = task.lower()
    hard = [k for k in r["keywords_complex"] if k in low]
    med = [k for k in r["keywords_medium"] if k in low]
    if hard:
        score += 2
        reasons.append("复杂关键词: " + ", ".join(hard[:4]))
    elif med:
        score += 1
        reasons.append("中等关键词: " + ", ".join(med[:4]))
    if re.search(r"\b(1[0-9]{2,}|[2-9][0-9]{2,})\s*(行|words?)", low):
        score += 1
        reasons.append("长文输出")
    if task.count("\n") > 8:
        score += 1
        reasons.append("多段输入")
    tier = "simple" if score <= 0 else "medium" if score <= 1 else "complex"
    if score >= 4:
        tier = "heavy"
    reasons.append(f"score={score}")
    return tier, reasons


def backend_for_tier(tier: str, cfg: dict) -> str:
    return cfg["routing"]["tiers"].get(tier, "deepseek-flash")


# ---------------------------------------------------------------- commands
def cmd_doctor(args) -> int:
    cfg = load_config()
    env = load_env()
    ok = True
    print("== 本地 Ollama ==")
    try:
        tags = http_json("http://127.0.0.1:11434/api/tags", timeout=8)
        names = [m["name"] for m in tags.get("models", [])]
        print(f"  ✓ 服务在线，{len(names)} 个模型: {', '.join(names[:6])}")
        for bname, b in cfg["backends"].items():
            if b.get("kind") == "ollama":
                mark = "✓" if b["model"] in names else "✗ 未下载"
                print(f"    {mark} {bname} → {b['model']}")
                ok = ok and b["model"] in names
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ Ollama 不可达: {e}")
        ok = False

    print("== 托管 API ==")
    for bname, b in cfg["backends"].items():
        if b.get("kind") != "openai":
            continue
        kname = b.get("key_env", "")
        has = bool(env.get(kname))
        print(f"  {'✓' if has else '✗'} {bname} ({b['model']}) key={kname}{'' if has else ' 未设置'}")
        ok = ok and has
    key = env.get("DEEPSEEK_API_KEY", "")
    if key:
        try:
            bal = http_json("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {key}"}, timeout=15)
            for info in bal.get("balance_infos", []):
                print(f"    DeepSeek 余额: {info.get('total_balance')} {info.get('currency')}")
        except Exception as e:  # noqa: BLE001
            print(f"    ! 余额查询失败: {e}")

    print("== 桌面 App ==")
    for aname, app in cfg["apps"].items():
        if app.get("disabled"):
            print(f"  – {aname:10s} 已停用（无自定义模型接口，仅 handoff 可选）")
            continue
        exe = Path(app.get("exe", ""))
        print(f"  {'✓' if exe.exists() else '✗'} {aname:10s} {app.get('configure'):13s} {exe}")
        ok = ok and exe.exists()
    wb = cfg["apps"]["workbuddy"]["models_json"]
    print(f"  {'✓' if Path(wb).exists() else '·'} WorkBuddy models.json: {wb}")

    print("== 计量 ==")
    recs = read_ledger()
    print(f"  ✓ 账本 {len(recs)} 条记录 → {cfg['paths']['ledger']}")
    st = budget_state(cfg)
    if st["cap"]:
        label = {"day": "每日", "month": "每月"}.get(st["period"], "累计")
        print(f"  ✓ {label}预算 ¥{st['cap']:.2f} · 已花 ¥{st['spent']:.4f} · 剩余 ¥{st['remaining']:.4f}")
    dsh = cfg["apps"]["dsh"].get("usage_file")
    if dsh and Path(dsh).exists():
        print(f"  ✓ DeepSeek Harness 账本可读: {dsh}")
    return 0 if ok else 1


def cmd_models(args) -> int:
    cfg = load_config()
    if args.action == "list":
        print(f"{'backend':16s} {'tier':10s} {'kind':8s} model / target")
        for name, b in cfg["backends"].items():
            tier = ",".join(b.get("tiers", []))
            target = b.get("model") or b.get("app", "")
            print(f"{name:16s} {tier:10s} {b['kind']:8s} {target}")
        print("\n路由: " + " | ".join(f"{k}→{v}" for k, v in cfg["routing"]["tiers"].items()))
        return 0
    if args.action == "set":
        name, model = args.name, args.model
        b = cfg["backends"].get(name)
        if not b:
            print(f"未知 backend: {name}（可用: {', '.join(cfg['backends'])}）", file=sys.stderr)
            return 2
        b["model"] = model
        if args.base_url:
            b["base_url"] = args.base_url
        if args.label:
            b["label"] = args.label
        save_config(cfg)
        print(f"✓ {name} → {model}" + (f" @ {args.base_url}" if args.base_url else ""))
        if b.get("kind") == "openai":
            print("  提示: 该后端还可在 Hermes 里用 /model 切到对应 alias。运行 `mbus sync` 同步到桌面 App。")
        return 0
    if args.action == "use":
        cfg["routing"]["tiers"][args.tier] = args.backend
        save_config(cfg)
        print(f"✓ tier {args.tier} → {args.backend}")
        return 0
    print("用法: mbus models [list|set <backend> <model>|use <tier> <backend>]", file=sys.stderr)
    return 2


def cmd_classify(args) -> int:
    cfg = load_config()
    tier, reasons = classify(args.task, cfg)
    print(f"tier={tier}  backend={backend_for_tier(tier, cfg)}")
    for r in reasons:
        print(f"  · {r}")
    return 0


def cmd_run(args) -> int:
    cfg = load_config()
    backend = args.backend
    if not backend:
        tier, _ = classify(args.prompt, cfg)
        tier = args.tier or tier
        backend = backend_for_tier(tier, cfg)
    text = run_backend(backend, args.prompt, args.system, args.max_tokens, tid=args.task_id, force=args.force)
    if args.json:
        print(json.dumps({"backend": backend, "text": text}, ensure_ascii=False, indent=2))
    else:
        print(text)
    return 0


PLAN_SYSTEM = """你是任务分解器。把用户的复杂任务拆成可独立完成的子任务。
只输出 JSON，格式：{"subtasks":[{"id":1,"goal":"...","tier":"simple|medium|complex|heavy"}]}
规则：
- 3 到 6 个子任务；彼此尽量无依赖，能并行；
- tier 选型：抽取/改写/短问答=simple；写作/解释/轻代码=medium；推理/设计/多约束=complex；最难的综合判断=heavy；
- goal 写清楚输入、输出、验收标准，能让别人独立做完；
- 不要输出多余文字。"""


def cmd_dispatch(args) -> int:
    cfg = load_config()
    tid = args.task_id or task_id()
    task = args.task
    tier = args.tier or classify(task, cfg)[0]
    planner = args.planner or ("deepseek-flash" if tier != "simple" else backend_for_tier("medium", cfg))
    n = args.split
    if n == 1 and tier in ("simple", "medium"):
        text = run_backend(backend_for_tier(tier, cfg), task, tid=tid, force=args.force)
        print(text)
        return 0
    n = n or 3
    print(f"[mbus] 规划中（planner={planner}, 目标 {n} 个子任务）…", file=sys.stderr)
    raw = run_backend(planner, f"把下面任务拆成 {n} 个可并行子任务。\n\n任务：{task}",
                      system=PLAN_SYSTEM, max_tokens=1200, tid=tid, step=0, quiet=True, force=args.force)
    plan = extract_json(raw) or {"subtasks": []}
    subs = plan.get("subtasks") or []
    if not subs:
        print("[mbus] 规划失败，退回单路执行", file=sys.stderr)
        text = run_backend(backend_for_tier(tier, cfg), task, tid=tid, force=args.force)
        print(text)
        return 0
    print(f"[mbus] 子任务 {len(subs)} 个：")
    for s in subs:
        print(f"  {s.get('id')}. [{s.get('tier', 'medium')}{'/' + s['backend'] if s.get('backend') else ''}] {s.get('goal', '')[:90]}")
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    results: dict[int, dict] = {}

    def work(s: dict) -> None:
        bid = int(s.get("id", 0))
        be = s.get("backend") or backend_for_tier(s.get("tier", "medium"), cfg)
        note = ""
        if be in cfg["backends"] and cfg["backends"][be].get("kind") == "app":
            fallback = backend_for_tier(s.get("tier", "complex"), cfg)
            note = f"（原定 {be}，GUI App 无法无头执行，改走 {fallback}）"
            be = fallback
        try:
            cap = min(4000, cfg["backends"].get(be, {}).get("max_tokens", 4000) or 4000)
            t0 = time.time()
            results[bid] = {"goal": s.get("goal", ""), "backend": be, "note": note,
                            "text": run_backend(be, s.get("goal", ""), max_tokens=cap, tid=tid, step=bid, quiet=True, force=args.force)}
            print(f"[mbus] ✓ 子任务 {bid} 完成（{be}, {time.time()-t0:.0f}s）{note}", file=sys.stderr, flush=True)
        except Exception as e:  # noqa: BLE001
            results[bid] = {"goal": s.get("goal", ""), "backend": be, "note": note, "text": "", "error": str(e)}
            print(f"[mbus] ✗ 子任务 {bid} 失败（{be}）: {e}", file=sys.stderr, flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(subs))) as ex:
        list(ex.map(work, subs))

    blocks = []
    for s in subs:
        r = results.get(int(s.get("id", 0)), {})
        body = r.get("text") or f"（失败: {r.get('error')}）"
        blocks.append(f"### 子任务 {s.get('id')} · {r.get('backend', '?')}{r.get('note', '')}\n目标: {s.get('goal', '')}\n\n{body}")
    joined = "\n\n".join(blocks)
    if args.no_synth:
        print(joined)
        return 0
    print("[mbus] 综合中…", file=sys.stderr)
    final = run_backend(args.synth_backend or "deepseek-flash",
                        f"原始任务：{task}\n\n下面是各子任务的执行结果，请综合成一份直接可用的最终答案（去掉过程赘述，保留关键结论、代码、数据）。\n\n{joined}",
                        max_tokens=8000, tid=tid, step=99, quiet=True, force=args.force)
    print(final)
    print(f"\n---\n[mbus] task_id={tid} · 明细: mbus usage --task {tid}", file=sys.stderr)
    return 0


def extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def cmd_sync(args) -> int:
    """Render the shared model registry into each app's native config."""
    cfg = load_config()
    env = load_env()
    written = []
    # --- WorkBuddy / CodeBuddy: ~/.codebuddy/models.json (OpenAI-compatible)
    wb_path = Path(cfg["apps"]["workbuddy"]["models_json"])
    models = []
    for name, b in cfg["backends"].items():
        if b.get("kind") == "ollama":
            models.append({
                "id": name, "name": f"{b['label']} (local)", "vendor": "Ollama",
                "url": b["base_url"].rstrip("/") + "/v1/chat/completions",
                "apiKey": "ollama",
                "maxInputTokens": 60000, "maxOutputTokens": 8192,
                "supportsToolCall": True, "supportsImages": False,
            })
        elif b.get("kind") == "openai" and env.get(b.get("key_env", "")):
            models.append({
                "id": name, "name": b["label"], "vendor": "DeepSeek" if "deepseek" in b["base_url"] else "OpenAI",
                "url": b["base_url"].rstrip("/") + "/chat/completions",
                "apiKey": "${" + b["key_env"] + "}",
                "maxInputTokens": min(1000000, 200000), "maxOutputTokens": b.get("max_tokens", 8192),
                "supportsToolCall": True, "supportsImages": True,
            })
    payload = {"models": models, "availableModels": [m["id"] for m in models]}
    wb_path.parent.mkdir(parents=True, exist_ok=True)
    wb_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written.append(str(wb_path))
    print(f"✓ WorkBuddy/CodeBuddy ← {len(models)} 个模型: {', '.join(m['id'] for m in models)}")
    print("  重启 WorkBuddy 后，在模型选择器里即可看到这些条目（切哪个＝切模型）。")

    # --- Qoder Work app: selection file (model key only, catalog is server-side)
    q = cfg["apps"]["qoder"].get("models_json")
    if q:
        print(f"· Qoder 模型选择文件: {q} —— 目前是 auto；改成具体模型 key（如 auto / 自定义条目）后重启 Qoder 生效")
    # --- DeepSeek Harness: models configured in app UI; we surface the routing
    print("· DeepSeek Harness：模型在 Settings → Models 里配；mbus 直接读取它的 usage-ledger 做计量。")
    # --- Hermes aliases so /model can switch to the same names
    print("· Hermes 内可用 `hermes config set model_aliases.<alias> ...` 生成同名 alias（见 SKILL.md）")
    return 0


def cmd_handoff(args) -> int:
    """Deliver a task to a desktop app: clipboard + launch/focus, then paste."""
    cfg = load_config()
    app_key = args.app
    app = cfg["apps"].get(app_key)
    if not app:
        print(f"未知 app: {app_key}（可用: {', '.join(cfg['apps'])}）", file=sys.stderr)
        return 2
    task = args.task
    if args.file:
        task = Path(args.file).read_text(encoding="utf-8")
    prompt = f"请完成以下任务，并在结尾给出：1) 结论 2) 改动/产物清单 3) 你消耗的大致 token。\n\n{task}"
    # clipboard via native Windows clip (no deps)
    try:
        subprocess.run(["clip"], input=prompt.encode("utf-16le"), check=True, shell=False)
        print(f"✓ 任务已复制到剪贴板（{len(prompt)} 字符）")
    except Exception as e:  # noqa: BLE001
        print(f"! 剪贴板失败: {e}", file=sys.stderr)
    exe = app.get("exe")
    if exe and Path(exe).exists() and not args.no_launch:
        try:
            subprocess.Popen([exe], close_fds=True)
            print(f"→ 已启动 {app['name']}")
        except Exception as e:  # noqa: BLE001
            print(f"! 启动失败: {e}", file=sys.stderr)
    print(f"下一步：切到 {app['name']} → Ctrl+V → 回车。回来后在 Hermes 里说一声“收结果”，我用 computer_use 读回复并记入账本。")
    print(f"task_id={args.task_id or '（handoff 不自动记账，读回时补记）'}")
    return 0


def aggregate(records: list[dict], by: str, days: int) -> dict:
    cutoff = now() - dt.timedelta(days=days) if days and days > 0 else None
    out: dict[str, dict] = {}
    for r in records:
        try:
            ts = dt.datetime.fromisoformat(r["ts"])
        except Exception:  # noqa: BLE001
            continue
        if cutoff and ts < cutoff:
            continue
        key = r["ts"][:10] if by == "day" else r[by]
        g = out.setdefault(key, {"in": 0, "cache": 0, "out": 0, "cost": 0.0, "calls": 0, "ms": 0, "errors": 0})
        g["in"] += r.get("in", 0)
        g["cache"] += r.get("cache", 0)
        g["out"] += r.get("out", 0)
        g["cost"] += r.get("cost_cny", 0.0)
        g["calls"] += 1
        g["ms"] += r.get("latency_ms", 0)
        g["errors"] += 0 if r.get("ok", True) else 1
    return out


def fmt_int(n: int) -> str:
    return f"{n:,}"


def cmd_budget(args) -> int:
    cfg = load_config()
    if args.set is not None:
        cfg.setdefault("budget", {})["cny"] = float(args.set)
        if args.period:
            cfg["budget"]["period"] = args.period
        if args.soft:
            cfg["budget"]["hard"] = False
        save_config(cfg)
        print(f"✓ 预算上限 → ¥{args.set:.2f} / {cfg['budget'].get('period', 'month')}")
    st = budget_state(cfg)
    label = {"day": "每日", "month": "每月"}.get(st["period"], "累计")
    bar_w = 24
    filled = min(bar_w, int(round(bar_w * min(1.0, st["pct"] / 100))))
    bar = "█" * filled + "░" * (bar_w - filled)
    print(f"{label}预算 ¥{st['cap']:.2f}  [{bar}] {st['pct']:.1f}%")
    print(f"已花 ¥{st['spent']:.4f} · 剩余 ¥{st['remaining']:.4f}" + ("" if st["hard"] else " · 软限制（只提醒不拦截）"))
    return 0


# ---------------------------------------------------------------- qoder cn
def qoder_paths() -> tuple[Path, Path]:
    cfg = load_config()
    s = Path(cfg["apps"]["qoder"].get("settings_json") or (Path.home() / ".qoder-cn" / "settings.json"))
    m = Path(cfg["apps"]["qoder"].get("models_json") or (Path.home() / ".qoder-cn" / ".models" / "default"))
    return s, m


def backup_file(p: Path) -> Path:
    b = p.with_suffix(p.suffix + "." + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".bak")
    b.write_bytes(p.read_bytes())
    return b


def cmd_qoder(args) -> int:
    settings_path, models_path = qoder_paths()
    if args.action == "providers":
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        prov = data.get("providers") or {}
        if not prov:
            print("（Qoder CN 里还没有自定义 provider）")
        for pid, p in prov.items():
            models = ", ".join(m.get("model", "?") for m in (p.get("models") or []))
            print(f"{pid}\n  base={p.get('baseUrl')}  models=[{models}]  protocol={p.get('protocol')}")
        cur = json.loads(models_path.read_text(encoding="utf-8")) if models_path.exists() else {}
        print(f"\n当前选择: {cur.get('key')}  ({models_path})")
        return 0
    if args.action == "add":
        cfg = load_config()
        b = cfg["backends"].get(args.backend)
        if not b or b.get("kind") != "openai":
            print(f"只能从 openai 类 backend 添加，当前: {args.backend}", file=sys.stderr)
            return 2
        env = load_env()
        key = env.get(b.get("key_env", ""), "")
        if not key:
            print(f"缺少 {b.get('key_env')}，无法写入 provider", file=sys.stderr)
            return 2
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        prov = data.setdefault("providers", {})
        pid = "qoder-custom-" + str(uuid.uuid4())
        prov[pid] = {
            "baseUrl": b["base_url"].rstrip("/") + ("/v1" if not b["base_url"].rstrip("/").endswith("/v1") else ""),
            "apiKey": key,
            "type": "openai-compatible",
            "protocol": "openai",
            "authType": "bearer",
            "model": b["model"],
            "models": [{
                "model": b["model"],
                "displayName": b.get("label", b["model"]),
                "contextWindow": 200000,
                "maxOutputTokens": b.get("max_tokens", 8192),
                "capabilities": {"vision": True, "thinking": {"modes": ["enabled"], "supportsEffort": True,
                                                              "supportedEffortLevels": ["low", "high", "max"]}},
            }],
        }
        if args.dry_run:
            redacted = json.loads(json.dumps(prov[pid]))
            redacted["apiKey"] = "<from .env, not printed>"
            print(f"[dry-run] 将写入 provider {pid} → {settings_path}")
            print(json.dumps({pid: redacted}, ensure_ascii=False, indent=2)[:900])
            return 0
        bak = backup_file(settings_path)
        settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"✓ 已把 {b['model']} 写入 Qoder CN 自定义 provider")
        print(f"  provider id: {pid}")
        print(f"  备份: {bak}")
        print("  重启 Qoder CN 后，在模型选择器里会出现该条目（key 不打印）。")
        return 0
    if args.action == "set-model":
        key = args.key or args.backend
        if not key:
            print("用法: mbus qoder set-model <model_key>（如 qmodel_latest / qfmodel / dfmodel）", file=sys.stderr)
            return 2
        cur = json.loads(models_path.read_text(encoding="utf-8")) if models_path.exists() else {}
        cur["key"] = key
        cur.setdefault("scene", "app")
        cur["updatedAt"] = int(time.time() * 1000)
        bak = backup_file(models_path) if models_path.exists() else None
        if args.dry_run:
            print(f"[dry-run] 将把 {models_path} 的 key 改为 {key}：{json.dumps(cur, ensure_ascii=False)}")
            return 0
        models_path.write_text(json.dumps(cur, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"✓ Qoder CN 模型 key → {key}" + (f"（备份 {bak.name}）" if bak else ""))
        print("  重启 Qoder CN 生效；若回退到 auto，说明该 key 不适用，用 set-model 换回来。")
        return 0
    print("用法: mbus qoder [providers|add <backend>|set-model <key>]", file=sys.stderr)
    return 2


def cmd_usage(args) -> int:
    recs = read_ledger()
    if args.task:
        recs = [r for r in recs if r.get("task_id") == args.task]
    by = args.by or "backend"
    agg = aggregate(recs, by, args.days)
    if args.json:
        print(json.dumps(agg, ensure_ascii=False, indent=2))
        return 0
    if not agg:
        print("（账本为空）")
        return 0
    total = {"in": 0, "cache": 0, "out": 0, "cost": 0.0, "calls": 0}
    print(f"{by:18s} {'调用':>5s} {'输入':>10s} {'缓存命中':>10s} {'输出':>9s} {'花费(¥)':>9s} {'均延迟':>8s}")
    print("-" * 78)
    for k, g in sorted(agg.items(), key=lambda kv: -kv[1]["cost"]):
        avg = g["ms"] // max(1, g["calls"])
        print(f"{k:18s} {g['calls']:>5d} {fmt_int(g['in']):>10s} {fmt_int(g['cache']):>10s} {fmt_int(g['out']):>9s} {g['cost']:>9.4f} {avg:>6d}ms")
        total["in"] += g["in"]; total["cache"] += g["cache"]; total["out"] += g["out"]
        total["cost"] += g["cost"]; total["calls"] += g["calls"]
    print("-" * 78)
    print(f"{'合计':18s} {total['calls']:>5d} {fmt_int(total['in']):>10s} {fmt_int(total['cache']):>10s} {fmt_int(total['out']):>9s} {total['cost']:>9.4f}")
    window = f"最近 {args.days} 天" if args.days and args.days > 0 else "全部时间"
    print(f"\n{window} · 峰值时段价格×2 已计入 · 本地模型计 0 元")
    st = budget_state(load_config())
    if st["cap"]:
        label = {"day": "每日", "month": "每月"}.get(st["period"], "累计")
        print(f"{label}预算 ¥{st['cap']:.2f} · 已花 ¥{st['spent']:.4f} · 剩余 ¥{st['remaining']:.4f}（{st['pct']:.1f}%）")
    if args.html:
        p = render_widget(recs, args.days)
        print(f"\n看板: {p}")
    return 0


def cmd_ingest(args) -> int:
    """Pull real usage from DeepSeek Harness's own ledger (CNY, per day/provider/model)."""
    cfg = load_config()
    src = Path(cfg["apps"]["dsh"]["usage_file"])
    if not src.exists():
        print(f"未找到 DSH 账本: {src}", file=sys.stderr)
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))
    state_path = Path(cfg["paths"]["ingest_state"])
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    seen = set(state.get("dsh", []))
    new_records = []
    for day, providers in (data.get("days") or {}).items():
        for prov, models in providers.items():
            for model, u in models.items():
                key = f"{day}|{prov}|{model}"
                if key in seen:
                    continue
                new_records.append({
                    "ts": f"{day}T23:59:00+08:00",
                    "task_id": f"ingest-dsh-{day}",
                    "step": 0,
                    "backend": f"dsh:{prov}",
                    "model": model,
                    "provider": prov,
                    "kind": "app",
                    "in": u.get("inputTokens", 0),
                    "cache": u.get("cacheReadTokens", 0),
                    "out": u.get("outputTokens", 0),
                    "cost_cny": round(float(u.get("cost", 0) or 0), 6),
                    "latency_ms": 0,
                    "ok": True,
                    "source": "ledger:dsh",
                })
                seen.add(key)
    append_ledger(new_records)
    state["dsh"] = sorted(seen)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 从 DeepSeek Harness 导入 {len(new_records)} 条（{sum(r['cost_cny'] for r in new_records):.4f} 元）")
    return 0


def cmd_suggest(args) -> int:
    """本地按任务关键词推荐 skills/plugins（零 token）。"""
    import ui  # 同目录
    res = ui.suggest(args.task, args.app, args.limit)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    for app, items in res.items():
        print(f"{app:10s} {', '.join(items) if items else '（无匹配）'}")
    return 0


def cmd_bindings(args) -> int:
    """App → 模型 绑定表（由「模型选择」页写入）。"""
    path = ROOT / "bindings.json"
    data = json.loads(path.read_text(encoding="utf-8")).get("bindings", {}) if path.exists() else {}
    if not data:
        print("（还没有绑定，去 Hermes 侧边栏「模型选择」里设）")
        return 0
    cfg = load_config()
    print(f"{'app':10s} {'名称':16s} {'绑定模型':24s} skills/plugins")
    for app, b in data.items():
        name = (cfg["apps"].get(app) or {}).get("name", app)
        print(f"{app:10s} {name:16s} {str(b.get('model') or '—'):24s} "
              f"{len(b.get('skills') or [])}/{len(b.get('plugins') or [])}")
    return 0


def cmd_balance(args) -> int:
    env = load_env()
    key = env.get("DEEPSEEK_API_KEY", "")
    if not key:
        print("未设置 DEEPSEEK_API_KEY", file=sys.stderr)
        return 1
    bal = http_json("https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {key}"}, timeout=15)
    for i in bal.get("balance_infos", []):
        print(f"DeepSeek 余额: {i['total_balance']} {i['currency']}")
    return 0


# ---------------------------------------------------------------- widget
def render_widget(records: list[dict], days: int = 7) -> Path:
    cfg = load_config()
    by_model = aggregate(records, "model", days)
    by_day = aggregate(records, "day", days)
    st = budget_state(cfg)
    total_cost = sum(g["cost"] for g in by_model.values())
    total_in = sum(g["in"] + g["cache"] for g in by_model.values())
    total_out = sum(g["out"] for g in by_model.values())
    calls = sum(g["calls"] for g in by_model.values())
    maxcost = max([g["cost"] for g in by_model.values()] + [0.0001])
    day_keys = sorted(by_day)[-7:]
    daymax = max([by_day[d]["cost"] for d in day_keys] + [0.0001])
    bars = "".join(
        f'<div class="bar" title="{d}"><span style="height:{max(3, int(by_day[d]["cost"]/daymax*64))}px"></span><em>{d[5:]}</em></div>'
        for d in day_keys)
    def cost_cell(c: float) -> str:
        return "—" if c < 0.00001 else f"¥{c:.4f}"

    rows = "".join(
        f'<tr><td>{m}</td><td class="n">{g["calls"]}</td><td class="n">{fmt_int(g["in"])}</td>'
        f'<td class="n">{fmt_int(g["cache"])}</td><td class="n">{fmt_int(g["out"])}</td>'
        f'<td class="n">{cost_cell(g["cost"])}</td>'
        f'<td><div class="meter"><i style="width:{int(g["cost"]/maxcost*100)}%"></i></div></td></tr>'
        for m, g in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"]))
    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>模型用量</title></head>
<style>
  body{{margin:0;font-family:inherit;color:var(--foreground,#1f2328)}}
  .wrap{{display:flex;flex-direction:column;gap:14px;min-width:520px}}
  .kpis{{display:flex;gap:10px;flex-wrap:wrap}}
  .kpi{{border:1px solid var(--border,#333);border-radius:10px;padding:10px 14px;min-width:104px;background:var(--card,transparent)}}
  .kpi b{{display:block;font-size:19px;font-variant-numeric:tabular-nums;font-weight:650;letter-spacing:-.02em}}
  .kpi span{{font-size:11px;color:var(--muted-foreground,#9aa)}}
  .spark{{display:flex;gap:6px;align-items:flex-end;height:84px;border:1px solid var(--border,#333);border-radius:10px;padding:10px}}
  .bar{{display:flex;flex-direction:column;align-items:center;gap:4px;flex:1}}
  .bar span{{width:100%;background:var(--accent,#7aa2f7);border-radius:3px 3px 0 0;display:block}}
  .bar em{{font-size:9px;font-style:normal;color:var(--muted-foreground,#9aa)}}
  table{{border-collapse:collapse;width:100%;font-size:12px}}
  th{{text-align:left;font-weight:600;color:var(--muted-foreground,#9aa);border-bottom:1px solid var(--border,#333);padding:6px 8px}}
  td{{padding:6px 8px;border-bottom:1px solid color-mix(in oklab,var(--border,#333) 55%,transparent)}}
  td.n{{text-align:right;font-variant-numeric:tabular-nums}}
  .meter{{height:5px;border-radius:3px;background:color-mix(in oklab,var(--border,#333) 18%,transparent);min-width:70px}}
  .meter i{{display:block;height:100%;border-radius:3px;background:var(--accent,#7aa2f7)}}
  .foot{{font-size:10px;color:var(--muted-foreground,#9aa);display:flex;justify-content:space-between}}
</style>
<div class="wrap">
  <div class="kpis">
    <div class="kpi"><b>¥{total_cost:.4f}</b><span>{"近 " + str(days) + " 天" if days and days > 0 else "全部"}花费</span></div>
    <div class="kpi"><b>{fmt_int(total_in)}</b><span>输入 tokens(+缓存)</span></div>
    <div class="kpi"><b>{fmt_int(total_out)}</b><span>输出 tokens</span></div>
    <div class="kpi"><b>{calls}</b><span>调用次数</span></div>
    <div class="kpi"><b>¥{st['remaining']:.2f}</b><span>预算剩余 / ¥{st['cap']:.2f}</span></div>
  </div>
  <div class="spark">{bars or '<span style="color:var(--muted-foreground)">暂无数据</span>'}</div>
  <table><thead><tr><th>模型</th><th class="n">调用</th><th class="n">输入</th><th class="n">缓存</th><th class="n">输出</th><th class="n">花费</th><th>占比</th></tr></thead>
  <tbody>{rows or '<tr><td colspan="7">暂无记录</td></tr>'}</tbody></table>
  <div class="foot"><span>mbus · 峰值×2 / 本地免费</span><span>{now().strftime('%Y-%m-%d %H:%M')}</span></div>
</div></html>"""
    out = Path(cfg["paths"]["widget"])
    out.write_text(html, encoding="utf-8")
    return out


# ---------------------------------------------------------------- cli
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mbus", description="Hermes model bus")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="健康检查")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("models", help="查看/切换 backend 模型")
    p.add_argument("action", nargs="?", default="list", choices=["list", "set", "use"])
    p.add_argument("name", nargs="?")
    p.add_argument("model", nargs="?")
    p.add_argument("--base-url")
    p.add_argument("--label")
    p.add_argument("--tier", default=None)
    p.add_argument("--backend", default=None)
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("classify", help="路由判断")
    p.add_argument("task")
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("run", help="单次调用")
    p.add_argument("prompt")
    p.add_argument("--backend")
    p.add_argument("--tier", choices=["simple", "medium", "complex", "heavy"])
    p.add_argument("--system")
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--task-id")
    p.add_argument("--force", action="store_true", help="越过预算上限")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("dispatch", help="拆解 + 并行分发 + 综合")
    p.add_argument("task")
    p.add_argument("--split", type=int, default=3)
    p.add_argument("--tier", choices=["simple", "medium", "complex", "heavy"])
    p.add_argument("--planner")
    p.add_argument("--synth-backend")
    p.add_argument("--no-synth", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="越过预算上限")
    p.add_argument("--json", action="store_true")
    p.add_argument("--task-id")
    p.set_defaults(func=cmd_dispatch)

    p = sub.add_parser("sync", help="同步模型到桌面 App 配置")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("handoff", help="把任务交给 GUI App")
    p.add_argument("task", nargs="?", default="")
    p.add_argument("--app", required=True)
    p.add_argument("--file")
    p.add_argument("--task-id")
    p.add_argument("--no-launch", action="store_true")
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser("usage", help="用量/花费统计")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--by", choices=["model", "backend", "day", "task_id"], default="backend")
    p.add_argument("--task")
    p.add_argument("--html", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_usage)

    p = sub.add_parser("ingest", help="导入 App 自身账本")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("budget", help="预算上限/剩余")
    p.add_argument("--set", type=float, help="设置上限（元）")
    p.add_argument("--period", choices=["day", "month", "all"])
    p.add_argument("--soft", action="store_true", help="只提醒不拦截")
    p.set_defaults(func=cmd_budget)

    p = sub.add_parser("qoder", help="Qoder CN 模型/provider 管理")
    p.add_argument("action", nargs="?", default="providers", choices=["providers", "add", "set-model"])
    p.add_argument("backend", nargs="?", help="add 时：backend 名")
    p.add_argument("--key", help="set-model 时的 model key")
    p.add_argument("--dry-run", action="store_true", help="只打印将要写入的内容")
    p.set_defaults(func=cmd_qoder)

    p = sub.add_parser("bindings", help="App→模型 绑定表")
    p.set_defaults(func=cmd_bindings)

    p = sub.add_parser("suggest", help="按任务推荐 skills/plugins（本地）")
    p.add_argument("task")
    p.add_argument("--app")
    p.add_argument("--limit", type=int, default=3)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_suggest)

    p = sub.add_parser("balance", help="DeepSeek 余额")
    p.set_defaults(func=cmd_balance)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"[mbus] {e}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"[mbus] 网络错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
