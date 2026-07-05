import { useState, useEffect } from 'react'
import { Database, MessageSquare, ArrowRight, GitMerge, Zap, Share2 } from 'lucide-react'

const SOURCES = [
  { label: 'PostgreSQL',     color: '#336791' },
  { label: 'MongoDB',        color: '#589636' },
  { label: 'MySQL',          color: '#00758F' },
  { label: 'Elasticsearch',  color: '#FEC514' },
  { label: 'REST API',       color: '#6366f1' },
  { label: 'Amazon S3',      color: '#FF9900' },
  { label: 'Files',          color: '#7c5cfc' },
]

const STEPS = [
  {
    n: '01',
    icon: Database,
    color: '#7c5cfc',
    title: 'Connect data sources',
    desc: 'Point Lattice at your databases, files, REST APIs, or S3 buckets. Multiple sources can be added — they all accumulate into one graph.',
    action: 'connectors',
    actionLabel: 'Open Connectors',
  },
  {
    n: '02',
    icon: GitMerge,
    color: '#38bdf8',
    title: 'Graph is built automatically',
    desc: 'GliNER extracts named entities. OpenAI resolves duplicates and builds relationships. Everything is stored in FalkorDB with vector indexes.',
  },
  {
    n: '03',
    icon: MessageSquare,
    color: '#34d399',
    title: 'Query with natural language',
    desc: 'Ask questions in plain English. Lattice searches the knowledge graph semantically and generates grounded answers via GPT-4o.',
    action: 'chat',
    actionLabel: 'Start chatting',
  },
]

const FEATURES = [
  { icon: '⊞', title: 'Multi-source ingestion',  desc: 'PostgreSQL, MongoDB, MySQL, Elasticsearch, REST APIs, S3, and uploaded files — all merge into one unified graph.' },
  { icon: '◎', title: 'Entity extraction',        desc: 'GliNER + spaCy identify people, orgs, places, concepts. OpenAI merges duplicates across sources.' },
  { icon: '✦', title: 'Vector similarity search', desc: 'FalkorDB HNSW indexes enable sub-millisecond semantic search over entity embeddings.' },
  { icon: '↗', title: 'Streaming progress',       desc: 'Server-sent events stream chunk-level progress in real time as documents are processed.' },
]

export default function HomePage({ apiUrl, setPage }) {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    fetch(`${apiUrl}/graph/stats`)
      .then(r => r.json())
      .then(setStats)
      .catch(() => {})
  }, [apiUrl])

  const totalNodes = stats?.nodes?.reduce((s, n) => s + n.count, 0) ?? 0
  const totalEdges = stats?.edges?.reduce((s, e) => s + e.count, 0) ?? 0
  const hasData    = totalNodes > 0

  return (
    <div className="overflow-y-auto h-full">
      <div className="px-8 py-10 max-w-4xl mx-auto space-y-12">

        {/* ── Hero ── */}
        <div className="text-center space-y-5">
          <div className="relative inline-block">
            <div
              className="text-[64px] font-black leading-none select-none"
              style={{ background: 'linear-gradient(135deg,#7c5cfc,#c084fc)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
            >◈</div>
            <div
              className="absolute inset-0 text-[64px] font-black leading-none select-none blur-2xl opacity-30 pointer-events-none"
              style={{ background: 'linear-gradient(135deg,#7c5cfc,#c084fc)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
              aria-hidden="true"
            >◈</div>
          </div>

          <div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-100">Lattice</h1>
            <p className="text-slate-500 mt-2.5 text-[15px] max-w-lg mx-auto leading-relaxed">
              Connect your data sources, build a knowledge graph automatically,<br />
              and query everything with natural language.
            </p>
          </div>

          <div className="flex items-center justify-center gap-3">
            <button
              onClick={() => setPage('connectors')}
              className="flex items-center gap-2 px-5 py-2.5 bg-accent hover:bg-accent-2 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              <Database size={14} />
              Add a data source
            </button>
            {hasData && (
              <button
                onClick={() => setPage('chat')}
                className="flex items-center gap-2 px-5 py-2.5 bg-card border border-border hover:border-accent/40 text-slate-300 text-sm font-medium rounded-xl transition-colors"
              >
                <MessageSquare size={14} />
                Start chatting
              </button>
            )}
          </div>

          {/* Live graph stats */}
          {hasData && (
            <div className="inline-flex items-center gap-4 bg-card border border-border rounded-full px-5 py-2 text-sm">
              <span className="text-slate-300 font-medium">{totalNodes.toLocaleString()}</span>
              <span className="text-slate-600 text-xs">entities</span>
              <span className="w-px h-3 bg-border" />
              <span className="text-slate-300 font-medium">{totalEdges.toLocaleString()}</span>
              <span className="text-slate-600 text-xs">relations</span>
              <span className="w-px h-3 bg-border" />
              <button onClick={() => setPage('graph')} className="text-accent hover:text-accent-2 text-xs font-medium transition-colors">
                View graph →
              </button>
            </div>
          )}
        </div>

        {/* ── How it works ── */}
        <div>
          <div className="flex items-center gap-3 mb-5">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">How it works</p>
            <div className="flex-1 h-px bg-border" />
          </div>

          <div className="grid grid-cols-3 gap-px bg-border rounded-2xl overflow-hidden">
            {STEPS.map((step, i) => (
              <div key={i} className="bg-surface p-6 flex flex-col gap-4">
                <div className="flex items-center justify-between">
                  <div
                    className="w-9 h-9 rounded-xl flex items-center justify-center"
                    style={{ backgroundColor: `${step.color}18`, border: `1px solid ${step.color}35` }}
                  >
                    <step.icon size={17} style={{ color: step.color }} />
                  </div>
                  <span className="text-[11px] font-mono text-slate-700">{step.n}</span>
                </div>
                <div className="flex-1">
                  <h3 className="text-[13px] font-semibold text-slate-200 mb-1.5">{step.title}</h3>
                  <p className="text-[12px] text-slate-500 leading-relaxed">{step.desc}</p>
                </div>
                {step.action && (
                  <button
                    onClick={() => setPage(step.action)}
                    className="flex items-center gap-1.5 text-[12px] font-medium transition-colors"
                    style={{ color: step.color }}
                  >
                    {step.actionLabel} <ArrowRight size={12} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* ── Supported sources ── */}
        <div>
          <div className="flex items-center gap-3 mb-5">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">Supported sources</p>
            <div className="flex-1 h-px bg-border" />
          </div>

          <div className="bg-card border border-border rounded-2xl p-5">
            <div className="flex items-center gap-3 flex-wrap">
              {SOURCES.map(({ label, color }) => (
                <div key={label} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface border border-border text-[12px] text-slate-400">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color, boxShadow: `0 0 5px ${color}60` }} />
                  {label}
                </div>
              ))}
            </div>
            <p className="text-[11px] text-slate-600 mt-4 leading-relaxed">
              Ingest from any combination of these sources — each runs independently and all data accumulates in the same knowledge graph.
              Go to <button onClick={() => setPage('connectors')} className="text-accent hover:text-accent-2 transition-colors">Connectors</button> to start.
            </p>
          </div>
        </div>

        {/* ── Empty state nudge ── */}
        {!hasData && (
          <div className="bg-card border border-border rounded-2xl p-6 flex items-center gap-5">
            <div className="w-10 h-10 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center flex-shrink-0">
              <Zap size={18} className="text-accent" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-slate-200">Graph is empty</p>
              <p className="text-[12px] text-slate-500 mt-0.5">Add a data source and run an ingest to populate the knowledge graph.</p>
            </div>
            <button
              onClick={() => setPage('connectors')}
              className="flex-shrink-0 flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-2 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              <Database size={13} />
              Add source
            </button>
          </div>
        )}

        {/* ── Feature highlights ── */}
        <div>
          <div className="flex items-center gap-3 mb-5">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">Under the hood</p>
            <div className="flex-1 h-px bg-border" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            {FEATURES.map(({ icon, title, desc }) => (
              <div key={title} className="bg-card/60 border border-border rounded-xl p-5 space-y-2">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-accent text-[15px]">{icon}</span>
                  <h3 className="text-[13px] font-semibold text-slate-300">{title}</h3>
                </div>
                <p className="text-[12px] text-slate-600 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}
