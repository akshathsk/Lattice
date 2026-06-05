import { useState } from 'react'
import { ChevronRight, ChevronDown, Layers, Share2, MessageSquare } from 'lucide-react'

const STEP_META = {
  retrieval: { label: 'Retrieval',       Icon: Layers,         accent: 'text-blue-400',   badge: 'bg-blue-500/10 border-blue-500/20 text-blue-400' },
  graph:     { label: 'Graph Traversal', Icon: Share2,         accent: 'text-purple-400', badge: 'bg-purple-500/10 border-purple-500/20 text-purple-400' },
  prompt:    { label: 'LLM Prompt',      Icon: MessageSquare,  accent: 'text-emerald-400',badge: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' },
}

export default function DebugTrace({ steps }) {
  const [open, setOpen] = useState({})
  const toggle = k => setOpen(o => ({ ...o, [k]: !o[k] }))

  return (
    <div className="space-y-1.5 text-xs">
      {steps.map(step => {
        const meta  = STEP_META[step.step] ?? { label: step.label, Icon: Layers, accent: 'text-slate-400', badge: 'bg-slate-500/10 border-slate-500/20 text-slate-400' }
        const { Icon } = meta
        const isOpen = !!open[step.step]

        return (
          <div key={step.step} className="bg-surface border border-border rounded-xl overflow-hidden">
            {/* Header */}
            <button
              onClick={() => toggle(step.step)}
              className="w-full flex items-center gap-2.5 px-3.5 py-2.5 hover:bg-white/5 transition-colors text-left"
            >
              <Icon size={13} className={meta.accent} />
              <span className="font-semibold text-slate-300 flex-1">{meta.label}</span>
              <span className="text-slate-600 font-mono text-[10px] mr-1">{stepSummary(step)}</span>
              {isOpen
                ? <ChevronDown  size={12} className="text-slate-600 flex-shrink-0" />
                : <ChevronRight size={12} className="text-slate-600 flex-shrink-0" />
              }
            </button>

            {/* Body */}
            {isOpen && (
              <div className="border-t border-border px-3.5 pb-3.5">
                <StepBody step={step} meta={meta} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Per-step summary line ────────────────────────────────────────────────────

function stepSummary(step) {
  const d = step.detail ?? {}
  if (step.step === 'retrieval') return `${d.total_ranked ?? 0} chunks · ${d.path_b_entities ?? 0} entities`
  if (step.step === 'graph')     return `${d.nodes ?? 0} nodes · ${d.edges ?? 0} edges`
  if (step.step === 'prompt')    return `${d.model ?? ''} · ${d.messages ?? 0} msgs`
  return ''
}

// ── Body router ─────────────────────────────────────────────────────────────

function StepBody({ step, meta }) {
  if (step.step === 'retrieval') return <RetrievalBody step={step} meta={meta} />
  if (step.step === 'graph')     return <GraphBody     step={step} meta={meta} />
  if (step.step === 'prompt')    return <PromptBody    step={step} />
  return null
}

// ── Stat pill ───────────────────────────────────────────────────────────────

function StatPill({ label, value }) {
  return (
    <div className="bg-black/30 rounded-lg px-2.5 py-2 flex flex-col gap-0.5">
      <span className="text-[9px] text-slate-600 uppercase tracking-wide">{label}</span>
      <span className="text-slate-200 font-semibold">{value ?? '—'}</span>
    </div>
  )
}

// ── Retrieval ────────────────────────────────────────────────────────────────

function RetrievalBody({ step }) {
  const d  = step.detail ?? {}
  const entities = step.entities ?? []
  const chunks   = step.chunks   ?? []

  return (
    <div className="space-y-3 pt-3 font-mono">
      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-1.5">
        <StatPill label="Vector chunks" value={d.path_a_chunks} />
        <StatPill label="Graph entities" value={d.path_b_entities} />
        <StatPill label="Graph chunks"  value={d.path_b_chunks} />
        <StatPill label="Boosted"        value={d.boosted_chunks} />
        <StatPill label="Total ranked"   value={d.total_ranked} />
        <StatPill label="Embed dim"      value={d.embedding_dim} />
      </div>

      {/* Anchor entities */}
      {entities.length > 0 && (
        <div>
          <SectionLabel>Anchor entities</SectionLabel>
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {entities.map((e, i) => (
              <span key={i} className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-accent/10 border border-accent/20 text-[10px]">
                <span className="text-slate-300 font-medium">{e.name}</span>
                <span className="text-accent/70">{e.type}</span>
                <span className="text-slate-600">d={e.dist?.toFixed(3)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Top chunks */}
      {chunks.length > 0 && (
        <div>
          <SectionLabel>Top chunks</SectionLabel>
          <div className="space-y-1.5 mt-1.5">
            {chunks.map((c, i) => {
              const via = Array.isArray(c.via) ? c.via : c.via ? [c.via] : []
              return (
                <div key={i} className="bg-black/20 rounded-lg p-2.5">
                  <div className="flex items-center gap-2 mb-1.5">
                    {via.map(v => (
                      <span key={v} className={`
                        text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border
                        ${v === 'vector' ? 'bg-blue-500/10 border-blue-500/20 text-blue-400'
                          : v === 'graph' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                          : 'bg-amber-500/10 border-amber-500/20 text-amber-400'}
                      `}>{v}</span>
                    ))}
                    <span className="text-slate-500 text-[10px]">{c.collection}#{c.record_id}</span>
                    <span className="ml-auto text-emerald-400 text-[10px]">↑{c.score?.toFixed(3)}</span>
                  </div>
                  <p className="text-[10px] text-slate-500 leading-relaxed line-clamp-3">{c.preview}</p>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Graph ────────────────────────────────────────────────────────────────────

function GraphBody({ step }) {
  const d     = step.detail ?? {}
  const edges = step.edges  ?? []

  return (
    <div className="space-y-3 pt-3 font-mono">
      <div className="grid grid-cols-4 gap-1.5">
        <StatPill label="Anchors" value={d.anchors} />
        <StatPill label="Hops"    value={d.hops} />
        <StatPill label="Nodes"   value={d.nodes} />
        <StatPill label="Edges"   value={d.edges} />
      </div>
      {edges.length > 0 && (
        <div>
          <SectionLabel>Subgraph edges ({edges.length} shown)</SectionLabel>
          <div className="space-y-1 mt-1.5 max-h-52 overflow-y-auto">
            {edges.map((e, i) => (
              <div key={i} className="flex items-center gap-1.5 text-[10px] py-0.5">
                <span className="text-slate-400 truncate max-w-[120px]">{e.src}</span>
                <span className="text-slate-700">—</span>
                <span className="text-purple-400 font-medium">{e.rel}</span>
                <span className="text-slate-700">→</span>
                <span className="text-slate-400 truncate max-w-[120px]">{e.dst}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Prompt ───────────────────────────────────────────────────────────────────

function PromptBody({ step }) {
  const d    = step.detail  ?? {}
  const msgs = step.messages ?? []
  const [expanded, setExpanded] = useState({})
  const toggleMsg = i => setExpanded(e => ({ ...e, [i]: !e[i] }))

  return (
    <div className="space-y-3 pt-3 font-mono">
      <div className="grid grid-cols-2 gap-1.5">
        <StatPill label="Model"    value={d.model} />
        <StatPill label="Messages" value={d.messages} />
      </div>
      {msgs.length > 0 && (
        <div className="space-y-1.5">
          {msgs.map((m, i) => {
            const isOpen = !!expanded[i]
            const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content)
            const roleCfg = {
              system:    { label: 'SYSTEM',    cls: 'text-slate-500 bg-slate-800/50 border-slate-700/30' },
              user:      { label: 'USER',      cls: 'text-blue-400  bg-blue-900/20  border-blue-700/20' },
              assistant: { label: 'ASSISTANT', cls: 'text-emerald-400 bg-emerald-900/20 border-emerald-700/20' },
            }[m.role] ?? { label: m.role?.toUpperCase(), cls: 'text-slate-400 bg-slate-800/50 border-slate-700/30' }

            return (
              <div key={i} className={`rounded-lg border overflow-hidden ${roleCfg.cls}`}>
                <button
                  onClick={() => toggleMsg(i)}
                  className="w-full flex items-center justify-between px-3 py-2 hover:bg-white/5"
                >
                  <span className="text-[9px] font-bold tracking-widest">{roleCfg.label}</span>
                  <span className="text-[9px] text-slate-600">{content.length.toLocaleString()} chars</span>
                </button>
                {isOpen && (
                  <div className="px-3 pb-3 border-t border-white/5">
                    <pre className="text-[10px] text-slate-500 leading-relaxed whitespace-pre-wrap break-words max-h-64 overflow-y-auto mt-2">
                      {content.slice(0, 2000)}{content.length > 2000 ? '…' : ''}
                    </pre>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function SectionLabel({ children }) {
  return (
    <p className="text-[9px] font-bold uppercase tracking-widest text-slate-600">{children}</p>
  )
}
