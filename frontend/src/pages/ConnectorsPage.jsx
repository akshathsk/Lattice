import { useState, useEffect, useRef } from 'react'
import { CheckCircle, XCircle, Loader2, Database } from 'lucide-react'

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ConnectorsPage({ apiUrl }) {
  const [pgConfig, setPgConfig] = useState({
    host: 'localhost', port: '5432', dbname: 'contracts',
    user: 'lattice',  password: 'lattice123', tables: '',
  })
  const [mgConfig, setMgConfig] = useState({
    host: 'localhost', port: '27017', database: 'contracts_docs', collections: '',
  })

  // Fetch defaults from API (overrides hard-coded values)
  useEffect(() => {
    fetch(`${apiUrl}/connectors/defaults`)
      .then(r => r.json())
      .then(d => {
        if (d.postgres) setPgConfig(prev => ({
          ...prev,
          host:   d.postgres.host     ?? prev.host,
          port:   String(d.postgres.port ?? prev.port),
          dbname: d.postgres.database ?? prev.dbname,
          user:   d.postgres.user     ?? prev.user,
        }))
        if (d.mongo) setMgConfig(prev => ({
          ...prev,
          host:     d.mongo.host     ?? prev.host,
          port:     String(d.mongo.port ?? prev.port),
          database: d.mongo.database ?? prev.database,
        }))
      })
      .catch(() => {})
  }, [apiUrl])

  return (
    <div className="overflow-y-auto h-full">
      <div className="px-8 py-6">
        <div className="mb-6">
          <h1 className="text-lg font-semibold text-slate-100">Connectors</h1>
          <p className="text-xs text-slate-500 mt-0.5">Configure data sources and trigger ingestion</p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <ConnectorCard
            title="PostgreSQL"
            emoji="🐘"
            source="postgres"
            apiUrl={apiUrl}
            fields={[
              { id: 'host',     label: 'Host',     type: 'text',     half: true },
              { id: 'port',     label: 'Port',     type: 'number',   half: true },
              { id: 'dbname',   label: 'Database', type: 'text' },
              { id: 'user',     label: 'User',     type: 'text',     half: true },
              { id: 'password', label: 'Password', type: 'password', half: true },
              { id: 'tables',   label: 'Tables',   type: 'text',     hint: 'comma-separated, blank = all' },
            ]}
            config={pgConfig}
            setConfig={setPgConfig}
            buildBody={cfg => {
              const body = {
                connection: clean({
                  host: cfg.host, port: num(cfg.port),
                  dbname: cfg.dbname, user: cfg.user, password: cfg.password,
                }),
              }
              const t = csv(cfg.tables)
              if (t.length) body.tables = t
              return body
            }}
          />
          <ConnectorCard
            title="MongoDB"
            emoji="🍃"
            source="mongo"
            apiUrl={apiUrl}
            fields={[
              { id: 'host',        label: 'Host',        type: 'text',   half: true },
              { id: 'port',        label: 'Port',        type: 'number', half: true },
              { id: 'database',    label: 'Database',    type: 'text' },
              { id: 'collections', label: 'Collections', type: 'text',   hint: 'comma-separated, blank = all' },
            ]}
            config={mgConfig}
            setConfig={setMgConfig}
            buildBody={cfg => {
              const body = {
                connection: clean({
                  host: cfg.host, port: num(cfg.port), database: cfg.database,
                }),
              }
              const c = csv(cfg.collections)
              if (c.length) body.collections = c
              return body
            }}
          />
        </div>
      </div>
    </div>
  )
}

// ── Connector card ────────────────────────────────────────────────────────────

function ConnectorCard({ title, emoji, source, apiUrl, fields, config, setConfig, buildBody }) {
  const [testing,  setTesting]  = useState(false)
  const [testMsg,  setTestMsg]  = useState(null)   // null | {ok, text}
  const [ingesting, setIngesting] = useState(false)
  const [ingest,   setIngest]   = useState(null)   // null | ingest state
  const logRef = useRef(null)

  const testConnection = async () => {
    setTesting(true)
    setTestMsg(null)
    try {
      const res = await fetch(`${apiUrl}/connectors/${source}/test`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ connection: buildBody(config).connection }),
      })
      if (res.ok) setTestMsg({ ok: true, text: 'Connection successful' })
      else {
        const d = await res.json().catch(() => ({}))
        setTestMsg({ ok: false, text: d.detail ?? `HTTP ${res.status}` })
      }
    } catch (e) {
      setTestMsg({ ok: false, text: e.message })
    } finally {
      setTesting(false)
    }
  }

  const runIngest = async () => {
    setIngesting(true)
    setTestMsg(null)
    setIngest({ progress: 0, total: 0, entities: 0, relations: 0, log: [], done: false, error: null, stats: null })

    try {
      const res = await fetch(`${apiUrl}/ingest/${source}`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(buildBody(config)),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''

        for (const part of parts) {
          const line = part.startsWith('data: ') ? part.slice(6) : part
          try {
            const evt = JSON.parse(line)

            if (evt.t === 'start') {
              setIngest(prev => ({ ...prev, total: evt.total }))
            } else if (evt.t === 'progress') {
              const logLine = {
                ok:   !evt.error,
                text: evt.error
                  ? `✗ ${evt.collection}#${evt.record_id} — ${evt.error}`
                  : `✓ ${evt.collection}#${evt.record_id} +${evt.entities}e +${evt.relations}r`,
              }
              setIngest(prev => ({
                ...prev,
                progress:  evt.current,
                total:     evt.total,
                entities:  evt.total_entities,
                relations: evt.total_relations,
                log: [...prev.log.slice(-59), logLine],
              }))
              // Auto-scroll log
              setTimeout(() => {
                if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
              }, 0)
            } else if (evt.t === 'done') {
              setIngest(prev => ({ ...prev, done: true, stats: evt }))
            } else if (evt.t === 'error') {
              setIngest(prev => ({ ...prev, done: true, error: evt.message }))
            }
          } catch { /* malformed */ }
        }
      }
    } catch (e) {
      setIngest(prev => ({ ...prev, done: true, error: e.message }))
    } finally {
      setIngesting(false)
    }
  }

  const busy = testing || ingesting
  const pct  = ingest?.total > 0 ? Math.round(ingest.progress / ingest.total * 100) : 0

  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-4 px-6 py-5 border-b border-border">
        <span className="text-3xl select-none">{emoji}</span>
        <div>
          <h2 className="text-[15px] font-semibold text-slate-100">{title}</h2>
          <span className="text-[10px] bg-surface border border-border text-slate-600 px-2 py-0.5 rounded-md font-mono">
            {source}
          </span>
        </div>
      </div>

      {/* Form */}
      <div className="px-6 py-5 space-y-5">
        <div className="grid grid-cols-2 gap-3">
          {fields.map(f => (
            <label key={f.id} className={`block ${!f.half ? 'col-span-2' : ''}`}>
              <span className="block text-[11px] text-slate-500 mb-1">
                {f.label}
                {f.hint && <span className="text-slate-700 ml-1">({f.hint})</span>}
              </span>
              <input
                type={f.type}
                value={config[f.id] ?? ''}
                onChange={e => setConfig(prev => ({ ...prev, [f.id]: e.target.value }))}
                className="
                  w-full bg-surface border border-border rounded-lg px-3 py-2
                  text-sm text-slate-200 font-mono outline-none
                  focus:border-accent/40 transition-colors placeholder-slate-700
                "
              />
            </label>
          ))}
        </div>

        {/* Action buttons */}
        <div className="flex gap-3">
          <button
            onClick={testConnection}
            disabled={busy}
            className="
              flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium
              bg-surface border border-border-2 text-slate-300
              hover:bg-card-2 disabled:opacity-50 transition-colors
            "
          >
            {testing ? <Loader2 size={13} className="animate-spin" /> : <Database size={13} />}
            Test
          </button>
          <button
            onClick={runIngest}
            disabled={busy}
            className="
              flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold
              bg-accent hover:bg-accent-2 text-white disabled:opacity-50 transition-colors
            "
          >
            {ingesting && <Loader2 size={13} className="animate-spin" />}
            {ingesting ? 'Ingesting…' : 'Run Ingest'}
          </button>
        </div>

        {/* Test result */}
        {testMsg && (
          <div className={`flex items-center gap-2 text-sm ${testMsg.ok ? 'text-emerald-400' : 'text-red-400'}`}>
            {testMsg.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
            {testMsg.text}
          </div>
        )}

        {/* Ingest progress */}
        {ingest && (
          ingest.done
            ? ingest.error
              ? <ErrorBox msg={ingest.error} />
              : <DoneBox stats={ingest.stats} />
            : <ProgressBox ingest={ingest} pct={pct} logRef={logRef} />
        )}
      </div>
    </div>
  )
}

// ── Ingest sub-components ─────────────────────────────────────────────────────

function ProgressBox({ ingest, pct, logRef }) {
  return (
    <div className="space-y-2.5">
      <div className="flex justify-between text-xs text-slate-500">
        <span>{ingest.progress}/{ingest.total} chunks</span>
        <span>{ingest.entities} entities · {ingest.relations} relations</span>
      </div>
      <div className="h-1.5 bg-surface rounded-full overflow-hidden">
        <div
          className="h-full bg-accent rounded-full transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      {ingest.log.length > 0 && (
        <div
          ref={logRef}
          className="bg-surface rounded-lg p-3 max-h-32 overflow-y-auto space-y-0.5"
        >
          {ingest.log.map((line, i) => (
            <p key={i} className={`text-[10px] font-mono ${line.ok ? 'text-slate-600' : 'text-red-400'}`}>
              {line.text}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

function DoneBox({ stats }) {
  const s = stats ?? {}
  const items = [
    ['Chunks',    s.ok_chunks],
    ['Entities',  s.total_entities],
    ['Relations', s.total_relations],
    ['Merged',    s.total_merged],
    ['Failed',    s.failed_chunks],
    ['Time',      s.elapsed_s != null ? `${s.elapsed_s}s` : '—'],
  ]
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-emerald-400">
        <CheckCircle size={14} />
        <span>Ingest complete{s.elapsed_s != null ? ` — ${s.elapsed_s}s` : ''}</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {items.map(([label, val]) => (
          <div key={label} className="bg-surface rounded-xl p-3 text-center">
            <p className="text-lg font-bold text-slate-200">{val ?? '—'}</p>
            <p className="text-[10px] text-slate-600 uppercase tracking-wide mt-0.5">{label}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function ErrorBox({ msg }) {
  return (
    <div className="flex items-center gap-2 text-sm text-red-400">
      <XCircle size={14} className="flex-shrink-0" />
      <span className="break-words">{msg}</span>
    </div>
  )
}

// ── Utilities ─────────────────────────────────────────────────────────────────

const clean = obj => Object.fromEntries(Object.entries(obj).filter(([, v]) => v != null && v !== ''))
const num   = s   => { const n = parseInt(s); return isNaN(n) ? undefined : n }
const csv   = s   => (s || '').split(',').map(x => x.trim()).filter(Boolean)
