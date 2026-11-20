/**
 * 模型选择 — Hermes desktop plugin（绑定版）
 *
 * 左侧栏「模型选择」页：给每个 App 绑定一个模型（选完即存），
 * 并给该 App 预设 skills / plugins。之后在下面写任务点「运行」，
 * Hermes 就按绑定用那个 App 的那个模型在后台跑，结果直接回到当前会话。
 *
 * 数据：http://127.0.0.1:8765（ui.py）；绑定存 model-bus/bindings.json。
 */
import { host, useValue, ROUTES_AREA, SIDEBAR_NAV_AREA, COMPOSER_AREAS } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'model-select'
const ENGINE = 'http://127.0.0.1:8765'
const PATH = '/model-select'

const SNAP = {"apps": [{"id": "local", "name": "本地 Ollama", "exec": "api", "models": [{"id": "local-4b", "label": "本地 Qwen3.5-4B", "kind": "api"}, {"id": "local-9b", "label": "本地 Qwen3.5-9B", "kind": "api"}], "skills": [], "plugins": [], "current": "", "bound": {"model": "local-9b", "skills": [], "plugins": []}}, {"id": "deepseek", "name": "DeepSeek API", "exec": "api", "models": [{"id": "deepseek-flash", "label": "DeepSeek V4.1 Flash (API)", "kind": "api"}, {"id": "deepseek-pro", "label": "DeepSeek V4-Pro (API)", "kind": "api"}], "skills": [], "plugins": [], "current": "", "bound": {"model": "deepseek-flash", "skills": [], "plugins": []}}, {"id": "qoder", "name": "Qoder CN", "exec": "gui", "models": [{"id": "Auto", "label": "Auto", "kind": "内置"}, {"id": "Qwen4-Max", "label": "Qwen4-Max", "kind": "内置"}, {"id": "Qwen4-Max-Preview", "label": "Qwen4-Max-Preview", "kind": "内置"}, {"id": "Qwen3.8-Max", "label": "Qwen3.8-Max", "kind": "内置"}, {"id": "Qwen3.8-Flash", "label": "Qwen3.8-Flash", "kind": "内置"}, {"id": "DeepSeek-V4-Pro", "label": "DeepSeek-V4-Pro", "kind": "内置"}, {"id": "DeepSeek-Flash", "label": "DeepSeek-Flash", "kind": "内置"}, {"id": "GLM-5.3", "label": "GLM-5.3", "kind": "内置"}, {"id": "GLM-5.3-Flash", "label": "GLM-5.3-Flash", "kind": "内置"}, {"id": "Kimi-K3.1-Pro", "label": "Kimi-K3.1-Pro", "kind": "内置"}, {"id": "Kimi-K2.8-Preview", "label": "Kimi-K2.8-Preview", "kind": "内置"}, {"id": "Step-5-Preview", "label": "Step-5-Preview", "kind": "内置"}, {"id": "MiniMax-M3.1-Flash", "label": "MiniMax-M3.1-Flash", "kind": "内置"}, {"id": "qoder-custom-2d381d5e-5d31-45c8-8828-d47ced5e6871", "label": "qwen3.5:4b-64k", "kind": "BYOK"}, {"id": "qoder-custom-32d5992e-7d3f-4034-9b95-9bb08f385876", "label": "deepseek-flash", "kind": "BYOK"}, {"id": "qoder-custom-aacad7dc-9206-4b19-a638-68a59c7737f3", "label": "qwen3.5:9b-64k", "kind": "BYOK"}], "skills": ["Skillsmith", "UI-UX-Intelligence-Expert", "ai-painting", "analytics-data-analysis", "analyze-code", "analyze-prompt", "api-scaffolding-backend-architect", "baoyu-article-illustrator", "beatra", "content-research-writer", "ctrip-wendao", "deep-research", "ego-browser", "frontend-agent", "frontend-design", "h3-prompt-writing", "humanizer", "image-enhancer", "image-ocr", "lemo-opuscar", "libai-skill", "llm-prompt-optimizer", "minimax-h3-ai-video", "nodejs-security-guard", "notion-infographic", "painted-animation", "ppt-master", "ppt-visual-designer", "quickbi-smartq-chat", "remotion", "render-deploy", "requesting-code-review", "self-improving-agent", "tencentmap-map-assistant", "ui-designer"], "plugins": ["Presentations", "alibabacloud-core", "architecture-visualization", "better-harness", "browser-use", "computer-use", "design-review", "diagram-design", "office-docx", "office-excel", "qgraphflow", "qoder-context", "qoder-create-plugin", "qoder-memory", "security-scan", "superpowers", "wecom-unified"], "current": "qmodel_latest", "bound": {"model": "Qwen4-Max-Preview", "skills": [], "plugins": []}}, {"id": "workbuddy", "name": "WorkBuddy", "exec": "gui", "models": [{"id": "快速", "label": "快速", "kind": "内置"}, {"id": "均衡", "label": "均衡", "kind": "内置"}, {"id": "极致", "label": "极致", "kind": "内置"}, {"id": "Hy4", "label": "Hy4", "kind": "内置"}, {"id": "Hy4 flash", "label": "Hy4 flash", "kind": "内置"}, {"id": "DeepSeek-V4.1-Flash", "label": "DeepSeek-V4.1-Flash", "kind": "内置"}, {"id": "GLM-5.3", "label": "GLM-5.3", "kind": "内置"}, {"id": "GLM-5.3-Flash", "label": "GLM-5.3-Flash", "kind": "内置"}, {"id": "GLM-5.2", "label": "GLM-5.2", "kind": "内置"}, {"id": "Space-Bunny", "label": "Space-Bunny", "kind": "内置"}, {"id": "MiniMax-M3.1-Flash", "label": "MiniMax-M3.1-Flash", "kind": "内置"}, {"id": "Kimi-K3.1-Pro", "label": "Kimi-K3.1-Pro", "kind": "内置"}, {"id": "Kimi-K3", "label": "Kimi-K3", "kind": "内置"}, {"id": "Kimi-K2.8-Preview", "label": "Kimi-K2.8-Preview", "kind": "内置"}, {"id": "DeepSeek-V4-Pro", "label": "DeepSeek-V4-Pro", "kind": "内置"}, {"id": "Step-5-Preview", "label": "Step-5-Preview", "kind": "内置"}, {"id": "local-4b", "label": "本地 Qwen3.5-4B (local)", "kind": "自定义"}, {"id": "local-9b", "label": "本地 Qwen3.5-9B (local)", "kind": "自定义"}, {"id": "deepseek-flash", "label": "DeepSeek V4.1 Flash (API)", "kind": "自定义"}, {"id": "deepseek-pro", "label": "DeepSeek V4-Pro (API)", "kind": "自定义"}], "skills": ["beatra__skillhub", "chatcut-app-promo-guide", "chatcut-audio-processing-gen", "chatcut-auto-screen-recorder", "chatcut-beauty-retouch", "chatcut-caption-template-impl", "chatcut-create-motion-graphics", "chatcut-create-pixel-processor", "chatcut-digital-human", "chatcut-doctor", "chatcut-image-gen", "chatcut-lipsync", "chatcut-media-offer", "chatcut-multicam-sync", "chatcut-music", "chatcut-product-help", "chatcut-skill-creator", "chatcut-talking-head-guide", "chatcut-transcription", "chatcut-ugc-ad-guide", "chatcut-video-gen", "chatcut-video-translation", "chatcut-viral-video-cloner", "chatcut-visual-analysis", "chatcut-voice", "chatcut-voice-isolation", "chatcut-web-browser", "chatcut-widget-forms", "ctrip-wendao", "h3-prompt-writing", "libai__skillhub", "minimax-h3-ai-video__skillhub", "nano-banana-pro", "pdf", "ppt-master", "pptx", "tencentmap-map-assistant", "unclecheng-reduce-ai-perception-v2__skillhub"], "plugins": [], "current": "", "bound": {"model": "Hy4 flash", "skills": [], "plugins": []}}, {"id": "dsh", "name": "DeepSeek Harness", "exec": "gui", "models": [{"id": "deepseek V4.1-Flash", "label": "deepseek V4.1-Flash", "kind": "DeepSeek Account"}, {"id": "deepseek V4-Pro", "label": "deepseek V4-Pro", "kind": "DeepSeek Account"}, {"id": "auto", "label": "auto", "kind": "My API Key"}, {"id": "deepseek flash", "label": "deepseek flash", "kind": "My API Key"}, {"id": "GLM 5.3", "label": "GLM 5.3", "kind": "My API Key"}, {"id": "GLM 5.3-flash", "label": "GLM 5.3-flash", "kind": "My API Key"}], "skills": ["beatra", "chatcut-app-promo-guide", "chatcut-audio-processing-gen", "chatcut-auto-screen-recorder", "chatcut-beauty-retouch", "chatcut-caption-template-impl", "chatcut-create-motion-graphics", "chatcut-create-pixel-processor", "chatcut-digital-human", "chatcut-doctor", "chatcut-image-gen", "chatcut-lipsync", "chatcut-media-offer", "chatcut-multicam-sync", "chatcut-music", "chatcut-product-help", "chatcut-skill-creator", "chatcut-talking-head-guide", "chatcut-transcription", "chatcut-ugc-ad-guide", "chatcut-video-gen", "chatcut-video-translation", "chatcut-viral-video-cloner", "chatcut-visual-analysis", "chatcut-voice", "chatcut-voice-isolation", "chatcut-web-browser", "chatcut-widget-forms", "mnemon-memory-space-setup", "modelscope-model-engine-deploy"], "plugins": ["qq-agent-presets", "qq-mode-console"], "current": "auto", "bound": {"model": "auto", "skills": [], "plugins": []}}]}

const T = {
  dim: 'var(--ui-text-tertiary)',
  dim4: 'var(--ui-text-quaternary)',
  stroke: 'var(--ui-stroke-secondary)',
  accent: 'var(--ui-accent)'
}

function Chip({ on, children, onClick, faded }) {
  return jsx('button', {
    type: 'button',
    onClick,
    style: {
      cursor: 'pointer', fontSize: 11.5, lineHeight: 1.45, padding: '3px 10px', borderRadius: 999,
      border: `1px solid ${on ? T.accent : T.stroke}`,
      background: on ? 'color-mix(in oklab, var(--ui-accent) 14%, transparent)' : 'transparent',
      color: on ? 'inherit' : T.dim, opacity: faded ? 0.45 : 1
    },
    children
  })
}

function AppRow({ app, selected, onClick }) {
  return jsxs('div', {
    onClick,
    style: {
      cursor: 'pointer', padding: '8px 10px', borderRadius: 8,
      border: `1px solid ${selected ? T.accent : T.stroke}`,
      background: selected ? 'color-mix(in oklab, var(--ui-accent) 10%, transparent)' : 'transparent'
    },
    children: [
      jsx('div', { style: { fontSize: 13, fontWeight: 600 }, children: app.name }),
      jsx('div', { style: { fontSize: 11, color: T.dim4, marginTop: 2 },
        children: `${app.exec === 'api' ? '后台 API' : 'App 内执行'} · ${app.models.length} 个模型` })
    ]
  })
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true } catch (_) { return false }
}

const fmtTok = n => (n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'k' : String(n || 0))

function UsageChip() {
  const usage = useValue(host.state.focusedUsage)
  const [today, setToday] = useState(null)

  useEffect(() => {
    let live = true
    const pull = () => fetch(ENGINE + '/api/usage')
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .then(d => { if (live) setToday(d) })
      .catch(() => { if (live) setToday(null) })
    pull()
    const id = setInterval(pull, 30000)
    return () => { live = false; clearInterval(id) }
  }, [])

  const u = usage && typeof usage === 'object' ? usage : {}
  const tin = u.inputTokens ?? u.in ?? u.promptTokens ?? 0
  const tout = u.outputTokens ?? u.out ?? u.completionTokens ?? 0
  const cost = u.costUsd ?? u.costCny ?? 0
  const todaySpent = today && today.budget ? today.budget.spent : null

  if (!tin && !tout && todaySpent == null) return null

  return jsxs('button', {
    type: 'button',
    onClick: () => host.navigate('/usage'),
    title: '打开用量面板',
    style: {
      display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'flex-end',
      padding: '2px 10px 4px', fontSize: 10.5, color: T.dim4, fontVariantNumeric: 'tabular-nums',
      userSelect: 'none', background: 'transparent', border: 'none', cursor: 'pointer', width: '100%'
    },
    children: [
      jsx('span', { children: `↑ ${fmtTok(tin)}  ↓ ${fmtTok(tout)}` }),
      cost ? jsx('span', { children: `本会话 $${Number(cost).toFixed(4)}` }) : null,
      todaySpent != null ? jsx('span', { children: `今日 ¥${Number(todaySpent).toFixed(3)}` }) : null,
      jsx('span', { style: { opacity: .6 }, children: '用量 ›' })
    ]
  })
}

function Bubble({ m }) {
  return jsxs('div', { style: { display: 'flex', gap: 8, marginBottom: 10 }, children: [
    jsx('div', {
      style: { width: 24, height: 24, borderRadius: 12, flex: '0 0 24px', display: 'flex', alignItems: 'center',
               justifyContent: 'center', fontSize: 13, background: `color-mix(in oklab, ${m.color} 18%, transparent)` },
      children: m.emoji || '•'
    }),
    jsxs('div', { style: { flex: 1, minWidth: 0 }, children: [
      jsxs('div', { style: { display: 'flex', gap: 6, alignItems: 'baseline' }, children: [
        jsx('span', { style: { fontSize: 11.5, fontWeight: 600 }, children: m.name }),
        jsx('span', { style: { fontSize: 9.5, color: T.dim4 }, children: `第${m.round}轮` }),
        m.tokens && m.tokens.out
          ? jsx('span', { style: { marginLeft: 'auto', fontSize: 9.5, color: T.dim4 },
                          children: `${m.tokens.out} tok · ¥${(m.tokens.cost_cny || 0).toFixed(4)}` })
          : null
      ] }),
      jsx('div', {
        style: { fontSize: 12, lineHeight: 1.55, whiteSpace: 'pre-wrap', color: m.error ? 'var(--ui-danger, #e05561)' : 'inherit', marginTop: 2 },
        children: m.text
      })
    ] })
  ] })
}

function ChatPane() {
  const [task, setTask] = useState('')
  const [room, setRoom] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!room || room.status === 'done') return
    const id = setInterval(async () => {
      try {
        const r = await fetch(ENGINE + '/api/room/' + room.id)
        const d = await r.json()
        if (d.ok) setRoom(d.room)
      } catch (_) { /* 引擎抖动时忽略 */ }
    }, 1500)
    return () => clearInterval(id)
  }, [room && room.id, room && room.status])

  // 打开时载入最近一局，别让面板空白
  useEffect(() => {
    let live = true
    ;(async () => {
      try {
        const r = await fetch(ENGINE + '/api/rooms')
        const d = await r.json()
        const first = d && d.rooms && d.rooms[0]
        if (first && live) {
          const rr = await fetch(ENGINE + '/api/room/' + first.id)
          const dd = await rr.json()
          if (dd.ok && live) setRoom(dd.room)
        }
      } catch (_) { /* 引擎没开就算了 */ }
    })()
    return () => { live = false }
  }, [])

  async function start() {
    const t = task.trim()
    if (!t) { setErr('先写任务'); return }
    setBusy(true); setErr('')
    try {
      const r = await fetch(ENGINE + '/api/room', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: t, rounds: 2 })
      })
      const d = await r.json()
      if (!d.ok) throw new Error(d.error || '启动失败')
      setRoom(d.room)
    } catch (e) {
      setErr(e && e.message ? e.message : String(e))
    }
    setBusy(false)
  }

  const msgs = (room && room.messages) || []
  const perAgent = {}
  for (const m of msgs) {
    const k = m.agent
    perAgent[k] = perAgent[k] || { name: m.name, emoji: m.emoji, out: 0, cost: 0 }
    perAgent[k].out += (m.tokens && m.tokens.out) || 0
    perAgent[k].cost += (m.tokens && m.tokens.cost_cny) || 0
  }

  return jsxs('div', { style: { display: 'flex', flexDirection: 'column', height: '100%', fontSize: 12.5, minHeight: 0 }, children: [
    jsxs('div', { style: { padding: '8px 10px', borderBottom: `1px solid ${T.stroke}`, display: 'flex', alignItems: 'center', gap: 8 }, children: [
      jsx('div', { style: { fontWeight: 650 }, children: '群聊' }),
      jsx('div', { style: { fontSize: 10.5, color: T.dim4 }, children: room ? `${room.status} · ${msgs.length} 条` : '多模型协作' }),
      jsx('button', {
        type: 'button', onClick: () => { setRoom(null); setTask('') },
        style: { marginLeft: 'auto', cursor: 'pointer', fontSize: 10.5, padding: '2px 8px', borderRadius: 999,
                 border: `1px solid ${T.stroke}`, background: 'transparent', color: T.dim },
        children: '新建'
      })
    ] }),
    jsxs('div', { style: { flex: 1, overflow: 'auto', padding: '10px 10px 0', minHeight: 0 }, children: [
      msgs.length === 0
        ? jsx('div', { style: { color: T.dim4, fontSize: 11.5, lineHeight: 1.7 },
                       children: '写一个任务，几个模型会各自发言、互相补充，最后汇总成一份答案。过程在这里逐条出现。' })
        : msgs.map((m, i) => jsx(Bubble, { m }, i)),
      room && room.final ? jsxs('div', {
        style: { border: '1px solid var(--ui-accent)', borderRadius: 10, padding: 10, margin: '8px 0 12px' },
        children: [
          jsx('div', { style: { fontSize: 11, fontWeight: 650, marginBottom: 4 }, children: '汇总（由 Hermes 整理）' }),
          jsx('div', { style: { fontSize: 12, lineHeight: 1.6, whiteSpace: 'pre-wrap' }, children: room.final })
        ]
      }) : null,
      room && room.status !== 'done' ? jsx('div', { style: { fontSize: 10.5, color: T.dim4, paddingBottom: 10 }, children: '…成员发言中' }) : null
    ] }),
    Object.keys(perAgent).length ? jsx('div', {
      style: { display: 'flex', gap: 8, flexWrap: 'wrap', padding: '6px 10px', borderTop: `1px solid ${T.stroke}`, fontSize: 9.5, color: T.dim4 },
      children: Object.entries(perAgent).map(([k, v]) =>
        jsx('span', { children: `${v.emoji}${v.name} ${v.out}tok ¥${v.cost.toFixed(4)}` }, k))
    }) : null,
    jsxs('div', { style: { padding: 10, borderTop: `1px solid ${T.stroke}` }, children: [
      jsx('textarea', {
        value: task, onChange: e => setTask(e.target.value),
        placeholder: '要几个模型一起做什么？',
        style: { width: '100%', minHeight: 56, resize: 'vertical', padding: 8, borderRadius: 8,
                 border: `1px solid ${T.stroke}`, background: 'transparent', color: 'inherit',
                 fontSize: 12.5, fontFamily: 'inherit', outline: 'none' }
      }),
      jsxs('div', { style: { display: 'flex', gap: 8, marginTop: 6, alignItems: 'center' }, children: [
        jsx('button', {
          type: 'button', disabled: busy, onClick: start,
          style: { cursor: busy ? 'default' : 'pointer', padding: '6px 12px', borderRadius: 8, border: 'none',
                   background: 'var(--ui-accent)', color: '#0b1020', fontWeight: 650, fontSize: 12, opacity: busy ? 0.6 : 1 },
          children: busy ? '启动中…' : '开始群聊'
        }),
        err ? jsx('span', { style: { fontSize: 10.5, color: 'var(--ui-danger, #e05561)' }, children: err }) : null
      ] })
    ] })
  ] })
}

function Kpi({ value, label }) {
  return jsxs('div', {
    style: { border: `1px solid ${T.stroke}`, borderRadius: 10, padding: '10px 14px', minWidth: 120 },
    children: [
      jsx('div', { style: { fontSize: 18, fontWeight: 650, fontVariantNumeric: 'tabular-nums' }, children: value }),
      jsx('div', { style: { fontSize: 11, color: T.dim4, marginTop: 2 }, children: label })
    ]
  })
}

function UsagePage() {
  const [d, setD] = useState(null)
  useEffect(() => {
    let live = true
    const pull = () => fetch(ENGINE + '/api/usage')
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .then(x => { if (live) setD(x) })
      .catch(() => { if (live) setD(null) })
    pull()
    const id = setInterval(pull, 30000)
    return () => { live = false; clearInterval(id) }
  }, [])

  if (!d) {
    return jsx('div', { style: { padding: 24, fontSize: 13, color: T.dim }, children: '用量引擎离线（启动 model-bus/ui.py 后自动刷新）' })
  }
  const t = d.totals || {}
  const budget = d.budget || {}
  const days = Object.entries(d.by_day || {}).sort((a, b) => a[0].localeCompare(b[0])).slice(-14)
  const maxDay = Math.max(...days.map(([, g]) => g.cost), 0.0001)
  const models = Object.entries(d.by_model || {}).sort((a, b) => b[1].cost - a[1].cost)
  const maxCost = Math.max(...models.map(([, g]) => g.cost), 0.0001)

  return jsxs('div', { style: { height: '100%', overflow: 'auto', padding: '18px 24px', fontSize: 13 }, children: [
    jsxs('div', { style: { display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 14 }, children: [
      jsx('div', { style: { fontWeight: 650, fontSize: 15 }, children: '用量' }),
      jsx('div', { style: { fontSize: 11, color: T.dim4 }, children: '近 30 天 · 峰值×2 · 本地免费' })
    ] }),
    jsxs('div', { style: { display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 18 }, children: [
      jsx(Kpi, { value: `¥${(t.cost || 0).toFixed(4)}`, label: '总花费' }),
      jsx(Kpi, { value: fmtTok((t.in || 0) + (t.cache || 0)), label: '输入 tokens(+缓存)' }),
      jsx(Kpi, { value: fmtTok(t.out || 0), label: '输出 tokens' }),
      jsx(Kpi, { value: String(t.calls || 0), label: '调用次数' }),
      jsx(Kpi, { value: `¥${(budget.remaining || 0).toFixed(2)}`, label: `预算剩余 / ¥${budget.cap || 0}` })
    ] }),
    jsxs('div', { style: { border: `1px solid ${T.stroke}`, borderRadius: 10, padding: 12, marginBottom: 18 }, children: [
      jsx('div', { style: { fontSize: 11, color: T.dim4, marginBottom: 8 }, children: '每日花费' }),
      jsxs('div', { style: { display: 'flex', alignItems: 'flex-end', gap: 8, height: 90 }, children: days.map(([day, g]) =>
        jsxs('div', { style: { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }, children: [
          jsx('div', { style: { width: '100%', height: Math.max(3, Math.round(g.cost / maxDay * 70)),
                               background: 'var(--ui-accent)', borderRadius: '3px 3px 0 0' } }),
          jsx('div', { style: { fontSize: 9, color: T.dim4 }, children: day.slice(5) })
        ] }, day)) })
    ] }),
    jsxs('table', { style: { width: '100%', borderCollapse: 'collapse', fontSize: 12 }, children: [
      jsx('thead', { children: jsx('tr', { children: ['模型', '调用', '输入', '缓存', '输出', '花费', '占比'].map(h =>
        jsx('th', { style: { textAlign: h === '模型' ? 'left' : 'right', color: T.dim4, fontWeight: 600,
                            padding: '6px 8px', borderBottom: `1px solid ${T.stroke}` }, children: h }, h)) }) }),
      jsx('tbody', { children: models.map(([m, g]) => jsxs('tr', { children: [
        jsx('td', { style: { padding: '6px 8px' }, children: m }),
        jsx('td', { style: { padding: '6px 8px', textAlign: 'right' }, children: g.calls }),
        jsx('td', { style: { padding: '6px 8px', textAlign: 'right' }, children: fmtTok(g.in) }),
        jsx('td', { style: { padding: '6px 8px', textAlign: 'right' }, children: fmtTok(g.cache) }),
        jsx('td', { style: { padding: '6px 8px', textAlign: 'right' }, children: fmtTok(g.out) }),
        jsx('td', { style: { padding: '6px 8px', textAlign: 'right' }, children: g.cost ? `¥${g.cost.toFixed(4)}` : '—' }),
        jsx('td', { style: { padding: '6px 8px', width: 90 }, children:
          jsx('div', { style: { height: 5, borderRadius: 3, background: 'color-mix(in oklab, var(--ui-accent) 30%, transparent)' },
            children: jsx('div', { style: { height: '100%', width: `${Math.round(g.cost / maxCost * 100)}%`, background: 'var(--ui-accent)', borderRadius: 3 } }) }) })
      ] }, m)) })
    ] })
  ] })
}

function Page() {
  const focused = useValue(host.state.focusedSessionId)
  const [inv, setInv] = useState(SNAP)
  const [engine, setEngine] = useState('snapshot')
  const [appId, setAppId] = useState(SNAP.apps[0] ? SNAP.apps[0].id : 'local')
  const [prompt, setPrompt] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    fetch(ENGINE + '/api/inventory')
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .then(d => { if (live) { setInv(d); setEngine('live') } })
      .catch(() => { if (live) setEngine('snapshot') })
    return () => { live = false }
  }, [])

  const app = inv.apps.find(a => a.id === appId) || inv.apps[0]
  const bound = (app && app.bound) || { model: '', skills: [], plugins: [] }

  async function saveBinding(patch) {
    const next = { ...bound, ...patch }
    setInv(prev => ({
      ...prev,
      apps: prev.apps.map(a => (a.id === app.id ? { ...a, bound: next } : a))
    }))
    try {
      await fetch(ENGINE + '/api/bindings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ app: app.id, ...next })
      })
      setStatus(engine === 'live' ? '已保存' : '引擎离线，仅本地生效（未落盘）')
    } catch (e) {
      setStatus('保存失败: ' + (e && e.message ? e.message : String(e)))
    }
  }

  const toggle = (list, key, v) => saveBinding({ [key]: list.includes(v) ? list.filter(x => x !== v) : [...list, v] })

  async function recommend() {
    const task = prompt.trim()
    if (!task) { setStatus('先在右边写任务，我再按任务挑 skills'); return }
    try {
      const r = await fetch(ENGINE + '/api/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task, app: app.id })
      })
      const d = await r.json()
      const hits = (d && d.suggest && d.suggest[app.id]) || []
      if (!hits.length) { setStatus('没匹配到合适的 skill，保持原样'); return }
      const merged = Array.from(new Set([...bound.skills, ...hits])).slice(0, 5)
      await saveBinding({ skills: merged })
      setStatus(`按任务推荐：${hits.join(', ')}`)
    } catch (e) {
      setStatus('推荐失败（引擎离线？）')
    }
  }

  async function run() {
    if (!bound.model) { setStatus('这个 App 还没绑定模型'); return }
    if (!prompt.trim()) { setStatus('先写任务'); return }
    if (!focused) { setStatus('没有活动会话'); return }
    setBusy(true)
    const lines = [
      `[模型调度] App=${app.name} · 模型=${bound.model}（已绑定）`,
      app.workspace ? `工作区：${app.workspace}（在 App 里切到这个工作区执行）` : '',
      bound.skills.length ? `用这些 skills: ${bound.skills.join(', ')}` : '',
      bound.plugins.length ? `用这些 plugins: ${bound.plugins.join(', ')}` : '',
      '',
      prompt.trim()
    ].filter(Boolean)
    try {
      await host.request('prompt.submit', { session_id: focused, text: lines.join(String.fromCharCode(10)), display_kind: 'hidden' })
      setStatus('已交给 Hermes，后台执行，结果会出现在会话里')
      setBusy(false)
    } catch (e) {
      const copied = await copyText(lines.join(String.fromCharCode(10)))
      setStatus(`${copied ? '注入失败，已复制到剪贴板' : '发送失败'}: ${e && e.message ? e.message : String(e)}`)
      setBusy(false)
    }
  }

  return jsxs('div', {
    style: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', fontSize: 13 },
    children: [
      jsxs('div', {
        style: { display: 'flex', alignItems: 'center', gap: 10, padding: '14px 20px', borderBottom: `1px solid ${T.stroke}` },
        children: [
          jsx('div', { style: { fontWeight: 650, fontSize: 15 }, children: '模型选择' }),
          jsx('span', { style: { fontSize: 11, color: T.dim4 }, children: engine === 'live' ? '引擎在线' : '内置快照' }),
          jsx('div', { style: { marginLeft: 'auto', fontSize: 11.5, color: T.dim }, children: '给每个 App 绑定一个模型，选完即存' })
        ]
      }),
      jsxs('div', {
        style: { flex: 1, display: 'grid', gridTemplateColumns: '250px minmax(0,1fr) 360px', minHeight: 0 },
        children: [
          // 左：App 列表
          jsxs('div', { style: { borderRight: `1px solid ${T.stroke}`, padding: '14px 12px', display: 'flex', flexDirection: 'column', gap: 6, overflow: 'auto' }, children: [
            jsx('div', { style: { fontSize: 11.5, fontWeight: 600, color: T.dim, marginBottom: 2 }, children: 'App' }),
            ...inv.apps.map(a => jsx(AppRow, { app: a, selected: a.id === appId, onClick: () => { setAppId(a.id); setStatus('') } }, a.id))
          ] }),
          // 中：绑定模型 + skills + plugins
          jsxs('div', { style: { padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 16, overflow: 'auto' }, children: [
            jsxs('div', { style: { display: 'flex', flexDirection: 'column', gap: 7 }, children: [
              jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: 8 }, children: [
                jsx('div', { style: { fontSize: 11.5, fontWeight: 600, color: T.dim }, children: '绑定的模型' }),
                jsx('div', { style: { marginLeft: 'auto', fontSize: 11, color: T.dim4 }, children: app.exec === 'api' ? 'Hermes 直接调用这个模型' : 'Hermes 让这个 App 用它跑' })
              ] }),
              jsx('select', {
                value: bound.model,
                onChange: e => saveBinding({ model: e.target.value }),
                style: {
                  padding: '9px 10px', borderRadius: 8, border: `1px solid ${T.stroke}`,
                  background: 'transparent', color: 'inherit', fontSize: 13, fontFamily: 'inherit'
                },
                children: app.models.map(m => jsx('option', { value: m.id, children: `${m.label}${m.kind ? ' · ' + m.kind : ''}` }, m.id))
              }),
              app.current ? jsx('div', { style: { fontSize: 11, color: T.dim4 }, children: `App 自己当前选的是：${app.current}` }) : null
            ] }),
            app.skills && app.skills.length ? jsxs('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 }, children: [
              jsxs('div', { style: { display: 'flex', alignItems: 'center' }, children: [
                jsx('div', { style: { fontSize: 11.5, fontWeight: 600, color: T.dim }, children: '默认 skills' }),
                jsx('div', { style: { marginLeft: 'auto', fontSize: 11, color: T.dim4 }, children: `已选 ${bound.skills.length} / ${app.skills.length}` })
              ] }),
              jsx('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 5 }, children: app.skills.map(s =>
                jsx(Chip, { on: bound.skills.includes(s), onClick: () => toggle(bound.skills, 'skills', s), children: s }, s)) })
            ] }) : null,
            app.plugins && Object.keys(app.plugins).length ? jsxs('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 }, children: [
              jsx('div', { style: { fontSize: 11.5, fontWeight: 600, color: T.dim }, children: '默认 plugins' }),
              jsx('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 5 }, children: Object.entries(app.plugins).map(([k, on]) =>
                jsx(Chip, { on: bound.plugins.includes(k), faded: !on, onClick: () => toggle(bound.plugins, 'plugins', k), children: k }, k)) })
            ] }) : null
          ] }),
          // 右：任务
          jsxs('div', { style: { borderLeft: `1px solid ${T.stroke}`, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10 }, children: [
            jsxs('div', { style: { display: 'flex', alignItems: 'center', gap: 8 }, children: [
              jsx('div', { style: { fontSize: 11.5, fontWeight: 600, color: T.dim }, children: '任务' }),
              jsx('button', {
                type: 'button', onClick: recommend,
                style: { cursor: 'pointer', fontSize: 10.5, padding: '2px 8px', borderRadius: 999,
                         border: `1px solid ${T.stroke}`, background: 'transparent', color: T.dim },
                children: '按任务推荐 skills'
              }),
              jsx('div', { style: { marginLeft: 'auto', fontSize: 11, color: T.dim4 }, children: `${app.name} · ${bound.model || '未绑定'}` })
            ] }),
            jsx('textarea', {
              value: prompt,
              onChange: e => setPrompt(e.target.value),
              placeholder: '写任务，点运行 → Hermes 在后台用上面绑定的模型跑，结果直接出现在会话里',
              style: { minHeight: 200, resize: 'vertical', padding: 10, borderRadius: 8, border: `1px solid ${T.stroke}`,
                       background: 'transparent', color: 'inherit', fontSize: 13, fontFamily: 'inherit', outline: 'none', lineHeight: 1.6 }
            }),
            jsx('button', {
              type: 'button', disabled: busy, onClick: run,
              style: { padding: '9px 12px', borderRadius: 8, border: 'none', cursor: busy ? 'default' : 'pointer',
                       background: 'var(--ui-accent)', color: '#0b1020', fontWeight: 650, fontSize: 13, opacity: busy ? 0.6 : 1 },
              children: busy ? '发送中…' : '运行'
            }),
            status ? jsx('div', { style: { fontSize: 12, color: T.dim }, children: status }) : null,
            jsx('div', { style: { marginTop: 'auto', fontSize: 11, color: T.dim4, lineHeight: 1.7 },
              children: '绑定保存在 model-bus/bindings.json，Hermes 每次调用都读它。' })
          ] })
        ]
      })
    ]
  })
}

export default {
  id: ID,
  name: '模型选择',
  register(ctx) {
    ctx.register({
      id: 'model-usage-page', area: ROUTES_AREA, data: { path: '/usage' },
      render: () => jsx('iframe', {
        src: 'http://127.0.0.1:8765/usage',
        style: { width: '100%', height: '100%', border: 'none', background: '#07080a', display: 'block' }
      })
    })
    ctx.register({ id: 'model-usage-nav', area: SIDEBAR_NAV_AREA, data: { path: '/usage', label: '用量', codicon: 'graph' } })
    ctx.register({ id: 'chat-pane', area: 'panes', title: '群聊', data: { placement: 'right', width: 360 }, render: () => jsx(ChatPane, {}) })
    ctx.register({
      id: 'dispatch-page', area: ROUTES_AREA, data: { path: '/dispatch' },
      render: () => jsx('iframe', {
        src: 'http://127.0.0.1:8765/dispatch',
        style: { width: '100%', height: '100%', border: 'none', background: '#07080a', display: 'block' }
      })
    })
    ctx.register({ id: 'dispatch-nav', area: SIDEBAR_NAV_AREA, data: { path: '/dispatch', label: '调度台', codicon: 'circuit-board' } })
  }
}
