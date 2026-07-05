import { useState } from 'react'
import { Home, MessageSquare, Network, Plug2 } from 'lucide-react'

const NAV = [
  { id: 'home',       label: 'Home',       Icon: Home },
  { id: 'chat',       label: 'Chat',       Icon: MessageSquare },
  { id: 'graph',      label: 'Graph',      Icon: Network },
  { id: 'connectors', label: 'Connectors', Icon: Plug2 },
]

export default function Sidebar({ page, setPage, apiUrl, setApiUrl, health }) {
  return (
    <aside className="w-56 flex-shrink-0 flex flex-col bg-surface border-r border-border">
      {/* Logo */}
      <div className="px-4 pt-6 pb-5">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <span
              className="text-[22px] font-black leading-none"
              style={{ background: 'linear-gradient(135deg, #7c5cfc, #c084fc)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
            >◈</span>
            <span
              className="absolute inset-0 text-[22px] font-black leading-none blur-md opacity-50 select-none"
              style={{ background: 'linear-gradient(135deg, #7c5cfc, #c084fc)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
              aria-hidden="true"
            >◈</span>
          </div>
          <div>
            <span className="text-[15px] font-semibold tracking-tight text-slate-100">Lattice</span>
          </div>
        </div>
        <p className="text-[11px] text-slate-700 mt-2 ml-0.5 tracking-wide">Knowledge Graph</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 space-y-0.5">
        {NAV.map(({ id, label, Icon }) => {
          const active = page === id
          return (
            <button
              key={id}
              onClick={() => setPage(id)}
              className={`
                relative w-full flex items-center gap-3 pl-4 pr-3 py-2.5 rounded-xl text-[13px] font-medium
                transition-all duration-150 text-left
                ${active
                  ? 'bg-accent/12 text-slate-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-white/4 border border-transparent'
                }
              `}
            >
              {active && (
                <span className="absolute left-1.5 top-2.5 bottom-2.5 w-0.5 rounded-full bg-accent" />
              )}
              <Icon size={15} className={active ? 'text-accent' : ''} />
              {label}
            </button>
          )
        })}
      </nav>

      {/* API URL */}
      <div className="mx-3 mb-4 p-3 rounded-xl bg-card border border-border">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-600 mb-2">API</p>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={apiUrl}
            onChange={e => setApiUrl(e.target.value.replace(/\/$/, ''))}
            className="flex-1 bg-transparent text-[11px] text-slate-400 outline-none min-w-0 placeholder-slate-600"
          />
          <HealthDot health={health} />
        </div>
      </div>
    </aside>
  )
}

function HealthDot({ health }) {
  const cfg = {
    ok:       { color: 'bg-emerald-400',  glow: '0 0 6px #34d399', title: 'API reachable' },
    error:    { color: 'bg-red-400',       glow: '0 0 6px #f87171', title: 'API unreachable' },
    checking: { color: 'bg-amber-400 animate-pulse', glow: 'none',  title: 'Checking…' },
  }[health] ?? {}

  return (
    <div
      title={cfg.title}
      className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.color}`}
      style={{ boxShadow: cfg.glow }}
    />
  )
}
