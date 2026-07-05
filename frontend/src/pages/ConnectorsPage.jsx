import { useState, useEffect, useRef, useCallback } from 'react'
import { CheckCircle, XCircle, Loader2, Database, Upload, FileText, ChevronDown, ChevronUp, ArrowRight, PlusCircle } from 'lucide-react'

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ConnectorsPage({ apiUrl, setPage }) {
  const [pgConfig, setPgConfig] = useState({
    host: 'localhost', port: '5432', dbname: 'contracts',
    user: 'lattice', password: 'lattice123', tables: '',
  })
  const [mgConfig, setMgConfig] = useState({
    host: 'localhost', port: '27017', database: 'contracts_docs', collections: '',
  })
  const [myConfig, setMyConfig] = useState({
    host: 'localhost', port: '3306', dbname: '', user: '', password: '', tables: '',
  })
  const [esConfig, setEsConfig] = useState({
    host: 'localhost', port: '9200', user: '', password: '', index: '',
  })
  const [restConfig, setRestConfig] = useState({
    url: '', method: 'GET', auth_header: '', json_path: '',
  })
  const [s3Config, setS3Config] = useState({
    bucket: '', prefix: '', region: 'us-east-1', access_key: '', secret_key: '',
  })
  const [graphStats, setGraphStats] = useState(null)

  const reloadStats = useCallback(() => {
    fetch(`${apiUrl}/graph/stats`)
      .then(r => r.json())
      .then(setGraphStats)
      .catch(() => {})
  }, [apiUrl])

  useEffect(() => {
    reloadStats()
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

  const totalNodes = graphStats?.nodes?.reduce((s, n) => s + n.count, 0) ?? 0
  const totalEdges = graphStats?.edges?.reduce((s, e) => s + e.count, 0) ?? 0
  const hasData    = totalNodes > 0

  return (
    <div className="overflow-y-auto h-full">
      <div className="px-8 py-6 max-w-5xl mx-auto space-y-8">

        <div>
          <h1 className="text-[15px] font-semibold text-slate-100 tracking-tight">Data Sources</h1>
          <p className="text-[11px] text-slate-600 mt-0.5">Connect as many sources as you need — each one ingests independently into the same graph</p>
        </div>

        {/* Pipeline banner */}
        <PipelineBanner
          totalNodes={totalNodes} totalEdges={totalEdges}
          hasData={hasData} setPage={setPage} onRefresh={reloadStats}
        />

        {/* File upload */}
        <section>
          <SectionLabel icon="↑">Upload Documents</SectionLabel>
          <FileUploadCard apiUrl={apiUrl} onIngestDone={reloadStats} />
        </section>

        {/* Databases */}
        <section>
          <SectionLabel icon="⊟">Databases</SectionLabel>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

            <DbConnectorCard
              title="PostgreSQL" source="postgres" color="#336791" apiUrl={apiUrl}
              fields={[
                { id: 'host',     label: 'Host',     type: 'text',     half: true },
                { id: 'port',     label: 'Port',     type: 'number',   half: true },
                { id: 'dbname',   label: 'Database', type: 'text' },
                { id: 'user',     label: 'User',     type: 'text',     half: true },
                { id: 'password', label: 'Password', type: 'password', half: true },
                { id: 'tables',   label: 'Tables',   type: 'text',     hint: 'comma-separated, blank = all' },
              ]}
              config={pgConfig} setConfig={setPgConfig}
              onIngestDone={reloadStats}
              buildBody={cfg => {
                const body = { connection: clean({ host: cfg.host, port: num(cfg.port), dbname: cfg.dbname, user: cfg.user, password: cfg.password }) }
                const t = csv(cfg.tables); if (t.length) body.tables = t
                return body
              }}
            />

            <DbConnectorCard
              title="MongoDB" source="mongo" color="#589636" apiUrl={apiUrl}
              fields={[
                { id: 'host',        label: 'Host',        type: 'text',   half: true },
                { id: 'port',        label: 'Port',        type: 'number', half: true },
                { id: 'database',    label: 'Database',    type: 'text' },
                { id: 'collections', label: 'Collections', type: 'text',   hint: 'comma-separated, blank = all' },
              ]}
              config={mgConfig} setConfig={setMgConfig}
              onIngestDone={reloadStats}
              buildBody={cfg => {
                const body = { connection: clean({ host: cfg.host, port: num(cfg.port), database: cfg.database }) }
                const c = csv(cfg.collections); if (c.length) body.collections = c
                return body
              }}
            />

            <DbConnectorCard
              title="MySQL" source="mysql" color="#00758F" apiUrl={apiUrl}
              fields={[
                { id: 'host',     label: 'Host',     type: 'text',     half: true },
                { id: 'port',     label: 'Port',     type: 'number',   half: true },
                { id: 'dbname',   label: 'Database', type: 'text' },
                { id: 'user',     label: 'User',     type: 'text',     half: true },
                { id: 'password', label: 'Password', type: 'password', half: true },
                { id: 'tables',   label: 'Tables',   type: 'text',     hint: 'comma-separated, blank = all' },
              ]}
              config={myConfig} setConfig={setMyConfig}
              onIngestDone={reloadStats}
              buildBody={cfg => {
                const body = { connection: clean({ host: cfg.host, port: num(cfg.port), dbname: cfg.dbname, user: cfg.user, password: cfg.password }) }
                const t = csv(cfg.tables); if (t.length) body.tables = t
                return body
              }}
            />

            <DbConnectorCard
              title="Elasticsearch" source="elasticsearch" color="#FEC514" apiUrl={apiUrl}
              fields={[
                { id: 'host',     label: 'Host',           type: 'text',     half: true },
                { id: 'port',     label: 'Port',           type: 'number',   half: true },
                { id: 'user',     label: 'User',           type: 'text',     half: true },
                { id: 'password', label: 'Password / API Key', type: 'password', half: true },
                { id: 'index',    label: 'Index',          type: 'text',     hint: 'blank = all non-system indices' },
              ]}
              config={esConfig} setConfig={setEsConfig}
              onIngestDone={reloadStats}
              buildBody={cfg => ({
                connection: clean({ host: cfg.host, port: num(cfg.port), user: cfg.user, password: cfg.password, database: cfg.index }),
              })}
            />

          </div>
        </section>

        {/* APIs & Cloud */}
        <section>
          <SectionLabel icon="↗">APIs &amp; Cloud</SectionLabel>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

            <RestConnectorCard apiUrl={apiUrl} config={restConfig} setConfig={setRestConfig} onIngestDone={reloadStats} />
            <S3ConnectorCard   apiUrl={apiUrl} config={s3Config}   setConfig={setS3Config}   onIngestDone={reloadStats} />

          </div>
        </section>

      </div>
    </div>
  )
}

// ── Section label ─────────────────────────────────────────────────────────────

function SectionLabel({ children, icon }) {
  return (
    <div className="flex items-center gap-2.5 mb-3">
      {icon && <span className="font-mono text-accent text-[13px]">{icon}</span>}
      <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">
        {children}
      </p>
      <div className="flex-1 h-px bg-border" />
    </div>
  )
}

// ── Pipeline banner ───────────────────────────────────────────────────────────

const PIPE_SOURCES = [
  { label: 'PostgreSQL', color: '#336791' },
  { label: 'MongoDB',    color: '#589636' },
  { label: 'MySQL',      color: '#00758F' },
  { label: 'Elastic',    color: '#FEC514' },
  { label: 'REST API',   color: '#6366f1' },
  { label: 'Amazon S3',  color: '#FF9900' },
  { label: 'Files',      color: '#7c5cfc' },
]

function PipelineBanner({ totalNodes, totalEdges, hasData, setPage, onRefresh }) {
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden">
      <div className="flex items-stretch">
        {/* Sources side */}
        <div className="flex-1 p-5 space-y-3">
          <div>
            <p className="text-[13px] font-semibold text-slate-200">Multiple sources, one graph</p>
            <p className="text-[12px] text-slate-500 mt-1 leading-relaxed">
              Each connector ingests independently — ingest from any number of sources
              and all data accumulates in the same knowledge graph.
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {PIPE_SOURCES.map(({ label, color }) => (
              <div key={label} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-surface border border-border text-[11px] text-slate-500">
                <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
                {label}
              </div>
            ))}
          </div>
        </div>

        {/* Arrow divider */}
        <div className="flex items-center px-4 text-slate-700">
          <ArrowRight size={18} />
        </div>

        {/* Graph side */}
        <div className="w-44 flex-shrink-0 border-l border-border p-5 flex flex-col items-center justify-center gap-2 bg-surface/40">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center text-[18px] font-black select-none"
            style={{ background: 'linear-gradient(135deg,rgba(124,92,252,0.2),rgba(192,132,252,0.1))', border: '1px solid rgba(124,92,252,0.3)', color: '#9d7dff' }}
          >◈</div>
          {hasData ? (
            <>
              <div className="text-center">
                <p className="text-[13px] font-bold text-slate-200">{totalNodes.toLocaleString()}</p>
                <p className="text-[10px] text-slate-600">entities</p>
              </div>
              <div className="text-center">
                <p className="text-[13px] font-bold text-slate-200">{totalEdges.toLocaleString()}</p>
                <p className="text-[10px] text-slate-600">relations</p>
              </div>
              <button
                onClick={() => setPage('graph')}
                className="mt-1 text-[11px] text-accent hover:text-accent-2 transition-colors font-medium"
              >
                View graph →
              </button>
            </>
          ) : (
            <div className="text-center">
              <p className="text-[12px] text-slate-600">Empty graph</p>
              <p className="text-[10px] text-slate-700 mt-0.5">Ingest to populate</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── File upload card ──────────────────────────────────────────────────────────

const ACCEPTED        = '.txt,.md,.pdf,.docx,.csv,.json'
const ACCEPTED_LABELS = ['TXT', 'MD', 'PDF', 'DOCX', 'CSV', 'JSON']

function FileUploadCard({ apiUrl, onIngestDone }) {
  const [files, setFiles]       = useState([])
  const [dragging, setDragging] = useState(false)
  const [ingest, setIngest]     = useState(null)
  const [busy, setBusy]         = useState(false)
  const inputRef = useRef(null)
  const logRef   = useRef(null)

  const addFiles = useCallback(incoming => {
    setFiles(prev => {
      const next = [...prev]
      for (const f of incoming) {
        if (!next.find(x => x.name === f.name && x.size === f.size)) next.push(f)
      }
      return next
    })
  }, [])

  const onDrop = e => { e.preventDefault(); setDragging(false); addFiles([...e.dataTransfer.files]) }
  const removeFile = idx => setFiles(prev => prev.filter((_, i) => i !== idx))

  const runIngest = async () => {
    if (!files.length || busy) return
    setBusy(true)
    setIngest({ progress: 0, total: 0, entities: 0, relations: 0, log: [], done: false, error: null, stats: null })
    const form = new FormData()
    for (const f of files) form.append('files', f)
    try {
      const res = await fetch(`${apiUrl}/ingest/file`, { method: 'POST', body: form })
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail ?? `HTTP ${res.status}`) }
      await consumeSSE(res, setIngest, logRef)
      onIngestDone?.()
    } catch (e) {
      setIngest(prev => ({ ...prev, done: true, error: e.message }))
    } finally { setBusy(false) }
  }

  const reset = () => { setFiles([]); setIngest(null) }
  const pct = ingest?.total > 0 ? Math.round(ingest.progress / ingest.total * 100) : 0

  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden" style={{ borderTop: '2px solid rgba(124,92,252,0.2)' }}>
      <div className="px-6 py-5 space-y-4">
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !busy && inputRef.current?.click()}
          className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed py-8 cursor-pointer transition-colors select-none
            ${dragging ? 'border-accent/60 bg-accent/5' : 'border-border hover:border-slate-600 hover:bg-surface/40'}
            ${busy ? 'pointer-events-none opacity-50' : ''}`}
        >
          <Upload size={20} className="text-slate-500" />
          <p className="text-sm text-slate-400">Drop files here or <span className="text-accent">browse</span></p>
          <div className="flex gap-1.5 flex-wrap justify-center">
            {ACCEPTED_LABELS.map(l => (
              <span key={l} className="text-[10px] font-mono bg-surface border border-border text-slate-600 px-1.5 py-0.5 rounded">{l}</span>
            ))}
          </div>
          <input ref={inputRef} type="file" multiple accept={ACCEPTED} className="hidden" onChange={e => addFiles([...e.target.files])} />
        </div>

        {files.length > 0 && (
          <ul className="space-y-1.5">
            {files.map((f, i) => (
              <li key={i} className="flex items-center gap-2 bg-surface rounded-lg px-3 py-2">
                <FileText size={13} className="text-slate-500 flex-shrink-0" />
                <span className="text-xs text-slate-300 flex-1 truncate font-mono">{f.name}</span>
                <span className="text-[10px] text-slate-600">{fmtSize(f.size)}</span>
                {!busy && <button onClick={e => { e.stopPropagation(); removeFile(i) }} className="text-slate-700 hover:text-slate-400 transition-colors ml-1"><XCircle size={13} /></button>}
              </li>
            ))}
          </ul>
        )}

        <div className="flex gap-3">
          <button
            onClick={runIngest} disabled={!files.length || busy}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold bg-accent hover:bg-accent-2 text-white disabled:opacity-40 transition-colors"
          >
            {busy && <Loader2 size={13} className="animate-spin" />}
            {busy ? 'Ingesting…' : `Ingest ${files.length ? `${files.length} file${files.length > 1 ? 's' : ''}` : 'Files'}`}
          </button>
          {(files.length > 0 || ingest) && !busy && (
            <button onClick={reset} className="px-4 py-2 rounded-xl text-sm text-slate-400 bg-surface border border-border hover:bg-card-2 transition-colors">Clear</button>
          )}
        </div>

        {ingest && (ingest.done
          ? (ingest.error ? <ErrorBox msg={ingest.error} /> : <DoneBox stats={ingest.stats} />)
          : <ProgressBox ingest={ingest} pct={pct} logRef={logRef} />)}
      </div>
    </div>
  )
}

// ── DB connector card ─────────────────────────────────────────────────────────

function DbConnectorCard({ title, source, color = '#7c5cfc', apiUrl, fields, config, setConfig, buildBody, onIngestDone }) {
  const [testing,   setTesting]   = useState(false)
  const [testMsg,   setTestMsg]   = useState(null)
  const [ingesting, setIngesting] = useState(false)
  const [ingest,    setIngest]    = useState(null)
  const [expanded,  setExpanded]  = useState(false)
  const logRef = useRef(null)

  const testConnection = async () => {
    setTesting(true); setTestMsg(null)
    try {
      const res = await fetch(`${apiUrl}/connectors/${source}/test`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connection: buildBody(config).connection }),
      })
      if (res.ok) setTestMsg({ ok: true, text: 'Connection successful' })
      else { const d = await res.json().catch(() => ({})); setTestMsg({ ok: false, text: d.detail ?? `HTTP ${res.status}` }) }
    } catch (e) { setTestMsg({ ok: false, text: e.message }) }
    finally { setTesting(false) }
  }

  const runIngest = async () => {
    setIngesting(true); setTestMsg(null)
    setIngest({ progress: 0, total: 0, entities: 0, relations: 0, log: [], done: false, error: null, stats: null })
    try {
      const res = await fetch(`${apiUrl}/ingest/${source}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildBody(config)),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      await consumeSSE(res, setIngest, logRef)
      onIngestDone?.()
    } catch (e) { setIngest(prev => ({ ...prev, done: true, error: e.message })) }
    finally { setIngesting(false) }
  }

  const busy = testing || ingesting
  const pct  = ingest?.total > 0 ? Math.round(ingest.progress / ingest.total * 100) : 0

  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden" style={{ borderTop: `2px solid ${color}22` }}>
      <button
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-white/3 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}80` }} />
        <div className="flex-1 flex items-center gap-3 min-w-0">
          <h2 className="text-[14px] font-semibold text-slate-200">{title}</h2>
          <span className="text-[10px] font-mono bg-surface border border-border text-slate-600 px-1.5 py-0.5 rounded">{source}</span>
        </div>
        {expanded ? <ChevronUp size={13} className="text-slate-600" /> : <ChevronDown size={13} className="text-slate-600" />}
      </button>
      {expanded && <div className="h-px mx-5 bg-border" />}

      {expanded && (
        <div className="px-6 py-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            {fields.map(f => (
              <label key={f.id} className={`block ${!f.half ? 'col-span-2' : ''}`}>
                <span className="block text-[11px] text-slate-500 mb-1">
                  {f.label}{f.hint && <span className="text-slate-700 ml-1">({f.hint})</span>}
                </span>
                <input
                  type={f.type} value={config[f.id] ?? ''}
                  onChange={e => setConfig(prev => ({ ...prev, [f.id]: e.target.value }))}
                  className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-200 font-mono outline-none focus:border-accent/40 transition-colors placeholder-slate-700"
                />
              </label>
            ))}
          </div>

          <div className="flex gap-3">
            <button onClick={testConnection} disabled={busy}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium bg-surface border border-border-2 text-slate-300 hover:bg-card-2 disabled:opacity-50 transition-colors">
              {testing ? <Loader2 size={13} className="animate-spin" /> : <Database size={13} />}
              Test
            </button>
            <button onClick={runIngest} disabled={busy}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold bg-accent hover:bg-accent-2 text-white disabled:opacity-50 transition-colors">
              {ingesting && <Loader2 size={13} className="animate-spin" />}
              {ingesting ? 'Ingesting…' : 'Run Ingest'}
            </button>
          </div>

          {testMsg && (
            <div className={`flex items-center gap-2 text-sm ${testMsg.ok ? 'text-emerald-400' : 'text-red-400'}`}>
              {testMsg.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
              {testMsg.text}
            </div>
          )}

          {ingest && (ingest.done
            ? (ingest.error ? <ErrorBox msg={ingest.error} /> : <DoneBox stats={ingest.stats} />)
            : <ProgressBox ingest={ingest} pct={pct} logRef={logRef} />)}
        </div>
      )}
    </div>
  )
}

// ── REST API connector card ───────────────────────────────────────────────────

function RestConnectorCard({ apiUrl, config, setConfig, onIngestDone }) {
  const [testing,   setTesting]   = useState(false)
  const [testMsg,   setTestMsg]   = useState(null)
  const [ingesting, setIngesting] = useState(false)
  const [ingest,    setIngest]    = useState(null)
  const [expanded,  setExpanded]  = useState(false)
  const logRef = useRef(null)

  const testConnection = async () => {
    setTesting(true); setTestMsg(null)
    try {
      const res = await fetch(`${apiUrl}/connectors/rest/test`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: config.url, method: config.method, auth_header: config.auth_header || null }),
      })
      if (res.ok) setTestMsg({ ok: true, text: 'Endpoint reachable' })
      else { const d = await res.json().catch(() => ({})); setTestMsg({ ok: false, text: d.detail ?? `HTTP ${res.status}` }) }
    } catch (e) { setTestMsg({ ok: false, text: e.message }) }
    finally { setTesting(false) }
  }

  const runIngest = async () => {
    setIngesting(true); setTestMsg(null)
    setIngest({ progress: 0, total: 0, entities: 0, relations: 0, log: [], done: false, error: null, stats: null })
    try {
      const res = await fetch(`${apiUrl}/ingest/rest`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: config.url, method: config.method,
          auth_header: config.auth_header || null,
          json_path: config.json_path || null,
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      await consumeSSE(res, setIngest, logRef)
      onIngestDone?.()
    } catch (e) { setIngest(prev => ({ ...prev, done: true, error: e.message })) }
    finally { setIngesting(false) }
  }

  const busy = testing || ingesting
  const pct  = ingest?.total > 0 ? Math.round(ingest.progress / ingest.total * 100) : 0

  const restColor = '#6366f1'
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden" style={{ borderTop: `2px solid ${restColor}22` }}>
      <button
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-white/3 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: restColor, boxShadow: `0 0 6px ${restColor}80` }} />
        <div className="flex-1 flex items-center gap-3 min-w-0">
          <h2 className="text-[14px] font-semibold text-slate-200">REST API</h2>
          <span className="text-[10px] font-mono bg-surface border border-border text-slate-600 px-1.5 py-0.5 rounded">rest</span>
        </div>
        {expanded ? <ChevronUp size={13} className="text-slate-600" /> : <ChevronDown size={13} className="text-slate-600" />}
      </button>
      {expanded && <div className="h-px mx-5 bg-border" />}

      {expanded && (
        <div className="px-6 py-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <label className="block col-span-2">
              <span className="block text-[11px] text-slate-500 mb-1">Endpoint URL</span>
              <input type="text" value={config.url} placeholder="https://api.example.com/data"
                onChange={e => setConfig(p => ({ ...p, url: e.target.value }))}
                className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-200 font-mono outline-none focus:border-accent/40 transition-colors placeholder-slate-700" />
            </label>
            <label className="block">
              <span className="block text-[11px] text-slate-500 mb-1">Method</span>
              <input type="text" value={config.method} placeholder="GET"
                onChange={e => setConfig(p => ({ ...p, method: e.target.value }))}
                className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-200 font-mono outline-none focus:border-accent/40 transition-colors placeholder-slate-700" />
            </label>
            <label className="block">
              <span className="block text-[11px] text-slate-500 mb-1">Auth Header</span>
              <input type="password" value={config.auth_header} placeholder="Bearer …"
                onChange={e => setConfig(p => ({ ...p, auth_header: e.target.value }))}
                className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-200 font-mono outline-none focus:border-accent/40 transition-colors placeholder-slate-700" />
            </label>
            <label className="block col-span-2">
              <span className="block text-[11px] text-slate-500 mb-1">JSON Path <span className="text-slate-700">(dot-notation to the items array, e.g. data.items)</span></span>
              <input type="text" value={config.json_path} placeholder="data.items"
                onChange={e => setConfig(p => ({ ...p, json_path: e.target.value }))}
                className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-200 font-mono outline-none focus:border-accent/40 transition-colors placeholder-slate-700" />
            </label>
          </div>

          <div className="flex gap-3">
            <button onClick={testConnection} disabled={busy || !config.url}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium bg-surface border border-border-2 text-slate-300 hover:bg-card-2 disabled:opacity-50 transition-colors">
              {testing ? <Loader2 size={13} className="animate-spin" /> : <Database size={13} />}
              Test
            </button>
            <button onClick={runIngest} disabled={busy || !config.url}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold bg-accent hover:bg-accent-2 text-white disabled:opacity-50 transition-colors">
              {ingesting && <Loader2 size={13} className="animate-spin" />}
              {ingesting ? 'Ingesting…' : 'Run Ingest'}
            </button>
          </div>

          {testMsg && (
            <div className={`flex items-center gap-2 text-sm ${testMsg.ok ? 'text-emerald-400' : 'text-red-400'}`}>
              {testMsg.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
              {testMsg.text}
            </div>
          )}

          {ingest && (ingest.done
            ? (ingest.error ? <ErrorBox msg={ingest.error} /> : <DoneBox stats={ingest.stats} />)
            : <ProgressBox ingest={ingest} pct={pct} logRef={logRef} />)}
        </div>
      )}
    </div>
  )
}

// ── S3 connector card ─────────────────────────────────────────────────────────

function S3ConnectorCard({ apiUrl, config, setConfig, onIngestDone }) {
  const [testing,   setTesting]   = useState(false)
  const [testMsg,   setTestMsg]   = useState(null)
  const [ingesting, setIngesting] = useState(false)
  const [ingest,    setIngest]    = useState(null)
  const [expanded,  setExpanded]  = useState(false)
  const logRef = useRef(null)

  const testConnection = async () => {
    setTesting(true); setTestMsg(null)
    try {
      const res = await fetch(`${apiUrl}/connectors/s3/test`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bucket: config.bucket, region: config.region, access_key: config.access_key || null, secret_key: config.secret_key || null }),
      })
      if (res.ok) setTestMsg({ ok: true, text: 'Bucket accessible' })
      else { const d = await res.json().catch(() => ({})); setTestMsg({ ok: false, text: d.detail ?? `HTTP ${res.status}` }) }
    } catch (e) { setTestMsg({ ok: false, text: e.message }) }
    finally { setTesting(false) }
  }

  const runIngest = async () => {
    setIngesting(true); setTestMsg(null)
    setIngest({ progress: 0, total: 0, entities: 0, relations: 0, log: [], done: false, error: null, stats: null })
    try {
      const res = await fetch(`${apiUrl}/ingest/s3`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bucket: config.bucket, prefix: config.prefix, region: config.region, access_key: config.access_key || null, secret_key: config.secret_key || null }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      await consumeSSE(res, setIngest, logRef)
      onIngestDone?.()
    } catch (e) { setIngest(prev => ({ ...prev, done: true, error: e.message })) }
    finally { setIngesting(false) }
  }

  const busy = testing || ingesting
  const pct  = ingest?.total > 0 ? Math.round(ingest.progress / ingest.total * 100) : 0
  const fields = [
    { id: 'bucket',     label: 'Bucket',     placeholder: 'my-bucket' },
    { id: 'prefix',     label: 'Prefix',     placeholder: 'docs/2024/' },
    { id: 'region',     label: 'Region',     placeholder: 'us-east-1' },
    { id: 'access_key', label: 'Access Key', placeholder: 'AKIA…' },
    { id: 'secret_key', label: 'Secret Key', placeholder: '••••', type: 'password' },
  ]

  const s3Color = '#FF9900'
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden" style={{ borderTop: `2px solid ${s3Color}22` }}>
      <button
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-white/3 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: s3Color, boxShadow: `0 0 6px ${s3Color}80` }} />
        <div className="flex-1 flex items-center gap-3 min-w-0">
          <h2 className="text-[14px] font-semibold text-slate-200">Amazon S3</h2>
          <span className="text-[10px] font-mono bg-surface border border-border text-slate-600 px-1.5 py-0.5 rounded">s3</span>
        </div>
        {expanded ? <ChevronUp size={13} className="text-slate-600" /> : <ChevronDown size={13} className="text-slate-600" />}
      </button>
      {expanded && <div className="h-px mx-5 bg-border" />}

      {expanded && (
        <div className="px-6 py-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            {fields.map(f => (
              <label key={f.id} className="block">
                <span className="block text-[11px] text-slate-500 mb-1">{f.label}</span>
                <input type={f.type ?? 'text'} value={config[f.id] ?? ''} placeholder={f.placeholder}
                  onChange={e => setConfig(p => ({ ...p, [f.id]: e.target.value }))}
                  className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-200 font-mono outline-none focus:border-accent/40 transition-colors placeholder-slate-700" />
              </label>
            ))}
          </div>

          <div className="flex gap-3">
            <button onClick={testConnection} disabled={busy || !config.bucket}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium bg-surface border border-border-2 text-slate-300 hover:bg-card-2 disabled:opacity-50 transition-colors">
              {testing ? <Loader2 size={13} className="animate-spin" /> : <Database size={13} />}
              Test
            </button>
            <button onClick={runIngest} disabled={busy || !config.bucket}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold bg-accent hover:bg-accent-2 text-white disabled:opacity-50 transition-colors">
              {ingesting && <Loader2 size={13} className="animate-spin" />}
              {ingesting ? 'Ingesting…' : 'Run Ingest'}
            </button>
          </div>

          {testMsg && (
            <div className={`flex items-center gap-2 text-sm ${testMsg.ok ? 'text-emerald-400' : 'text-red-400'}`}>
              {testMsg.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
              {testMsg.text}
            </div>
          )}

          {ingest && (ingest.done
            ? (ingest.error ? <ErrorBox msg={ingest.error} /> : <DoneBox stats={ingest.stats} />)
            : <ProgressBox ingest={ingest} pct={pct} logRef={logRef} />)}
        </div>
      )}
    </div>
  )
}

// ── Shared ingest sub-components ──────────────────────────────────────────────

function ProgressBox({ ingest, pct, logRef }) {
  return (
    <div className="space-y-2.5">
      <div className="flex justify-between text-xs text-slate-500">
        <span>{ingest.progress}/{ingest.total} chunks</span>
        <span>{ingest.entities} entities · {ingest.relations} relations</span>
      </div>
      <div className="h-1.5 bg-surface rounded-full overflow-hidden">
        <div className="h-full bg-accent rounded-full transition-all duration-300" style={{ width: `${pct}%` }} />
      </div>
      {ingest.log.length > 0 && (
        <div ref={logRef} className="bg-surface rounded-lg p-3 max-h-32 overflow-y-auto space-y-0.5">
          {ingest.log.map((line, i) => (
            <p key={i} className={`text-[10px] font-mono ${line.ok ? 'text-slate-600' : 'text-red-400'}`}>{line.text}</p>
          ))}
        </div>
      )}
    </div>
  )
}

function DoneBox({ stats }) {
  const s = stats ?? {}
  const items = [
    ['Chunks', s.ok_chunks], ['Entities', s.total_entities], ['Relations', s.total_relations],
    ['Merged', s.total_merged], ['Failed', s.failed_chunks], ['Time', s.elapsed_s != null ? `${s.elapsed_s}s` : '—'],
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

// ── Shared SSE consumer ───────────────────────────────────────────────────────

async function consumeSSE(res, setIngest, logRef) {
  const reader  = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n'); buf = parts.pop() ?? ''
    for (const part of parts) {
      const line = part.startsWith('data: ') ? part.slice(6) : part
      try {
        const evt = JSON.parse(line)
        if (evt.t === 'start') {
          setIngest(prev => ({ ...prev, total: evt.total }))
        } else if (evt.t === 'progress') {
          const logLine = {
            ok: !evt.error,
            text: evt.error
              ? `✗ ${evt.collection}#${evt.record_id} — ${evt.error}`
              : `✓ ${evt.collection}#${evt.record_id} +${evt.entities}e +${evt.relations}r`,
          }
          setIngest(prev => ({
            ...prev,
            progress: evt.current, total: evt.total,
            entities: evt.total_entities, relations: evt.total_relations,
            log: [...prev.log.slice(-59), logLine],
          }))
          setTimeout(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, 0)
        } else if (evt.t === 'done') {
          setIngest(prev => ({ ...prev, done: true, stats: evt }))
        } else if (evt.t === 'error') {
          setIngest(prev => ({ ...prev, done: true, error: evt.message }))
        }
      } catch { /* malformed */ }
    }
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────

const clean   = obj => Object.fromEntries(Object.entries(obj).filter(([, v]) => v != null && v !== ''))
const num     = s   => { const n = parseInt(s); return isNaN(n) ? undefined : n }
const csv     = s   => (s || '').split(',').map(x => x.trim()).filter(Boolean)
const fmtSize = b   => b < 1024 ? `${b}B` : b < 1024 ** 2 ? `${(b / 1024).toFixed(1)}KB` : `${(b / 1024 ** 2).toFixed(1)}MB`
