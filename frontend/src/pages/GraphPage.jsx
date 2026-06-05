import { useState, useRef, useEffect, useCallback } from 'react'
import { RefreshCw, Search, X, Info } from 'lucide-react'
import cytoscape from 'cytoscape'

// ── Color palette (12 hues) ──────────────────────────────────────────────────
const PALETTE = [
  '#7c5cfc','#38bdf8','#34d399','#fb923c','#f472b6',
  '#a78bfa','#22d3ee','#4ade80','#fbbf24','#f87171',
  '#e879f9','#2dd4bf',
]
function typeColor(type) {
  if (!type) return PALETTE[0]
  let h = 0
  for (let i = 0; i < type.length; i++) h = (h * 31 + type.charCodeAt(i)) >>> 0
  return PALETTE[h % PALETTE.length]
}

// ── Main component ───────────────────────────────────────────────────────────

export default function GraphPage({ apiUrl }) {
  const containerRef = useRef(null)
  const cyRef        = useRef(null)

  const [limit,    setLimit]    = useState(300)
  const [search,   setSearch]   = useState('')
  const [loading,  setLoading]  = useState(false)
  const [loaded,   setLoaded]   = useState(false)
  const [status,   setStatus]   = useState('Load the graph to start exploring')
  const [types,    setTypes]    = useState([])     // [{type, color, count, visible}]
  const [stats,    setStats]    = useState(null)
  const [selected, setSelected] = useState(null)

  // Destroy cytoscape on unmount
  useEffect(() => () => { cyRef.current?.destroy() }, [])

  // Search highlighting
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('search-match dimmed')
    const q = search.trim().toLowerCase()
    if (!q) return
    const matched = cy.nodes().filter(n => n.data('fullName').toLowerCase().includes(q))
    if (matched.length) {
      cy.elements().addClass('dimmed')
      matched.addClass('search-match').removeClass('dimmed')
      matched.neighborhood().removeClass('dimmed')
    }
  }, [search])

  // Type filter
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    types.forEach(t => {
      const nodes = cy.nodes().filter(n => n.data('type') === t.type)
      t.visible ? nodes.removeClass('hidden-type') : nodes.addClass('hidden-type')
    })
  }, [types])

  const loadGraph = useCallback(async () => {
    setLoading(true)
    setStatus('Fetching graph data…')
    try {
      const [dataRes, statsRes] = await Promise.all([
        fetch(`${apiUrl}/graph/data?limit=${limit}`),
        fetch(`${apiUrl}/graph/stats`),
      ])
      const { nodes, edges } = await dataRes.json()
      const statsData = await statsRes.json()

      if (!nodes?.length) {
        setStatus('No entities found — run an ingest first.')
        return
      }

      // Build type map
      const typeMap = {}
      nodes.forEach(n => {
        if (!typeMap[n.type]) typeMap[n.type] = { type: n.type, color: typeColor(n.type), count: 0, visible: true }
        typeMap[n.type].count++
      })
      const typeList = Object.values(typeMap).sort((a, b) => b.count - a.count)
      setTypes(typeList)
      setStats({ nodes: nodes.length, edges: edges.length, db: statsData })
      setLoaded(true)

      renderGraph(nodes, edges, typeMap)
    } catch (e) {
      setStatus('Failed to load: ' + e.message)
    } finally {
      setLoading(false)
    }
  }, [apiUrl, limit])

  const renderGraph = (nodes, edges, typeMap) => {
    cyRef.current?.destroy()
    const nodeSet = new Set(nodes.map(n => n.id))

    const elements = [
      ...nodes.map(n => ({
        data: {
          id:       n.id,
          label:    n.name.length > 24 ? n.name.slice(0, 22) + '…' : n.name,
          fullName: n.name,
          type:     n.type,
          color:    typeMap[n.type]?.color ?? PALETTE[0],
        },
      })),
      ...edges
        .filter(e => nodeSet.has(e.src) && nodeSet.has(e.dst))
        .map((e, i) => ({
          data: { id: `e${i}`, source: e.src, target: e.dst, label: e.type },
        })),
    ]

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: cytoscapeStyle(),
      layout: {
        name:            'cose',
        animate:         nodes.length < 200,
        animationDuration: 450,
        nodeRepulsion:   8000,
        idealEdgeLength: 80,
        edgeElasticity:  0.5,
        gravity:         0.25,
        numIter:         nodes.length < 200 ? 1000 : 500,
        fit:             true,
        padding:         40,
      },
      minZoom: 0.05,
      maxZoom: 6,
    })

    cy.on('tap', 'node', evt => {
      const node = evt.target
      const neighbors = node.neighborhood('node')
      setSelected({
        id:        node.id(),
        name:      node.data('fullName'),
        type:      node.data('type'),
        color:     node.data('color'),
        degree:    node.degree(),
        neighbors: neighbors.map(n => ({ name: n.data('fullName'), type: n.data('type') })),
      })
      cy.elements().addClass('dimmed')
      node.removeClass('dimmed')
      node.neighborhood().removeClass('dimmed')
    })

    cy.on('tap', evt => {
      if (evt.target === cy) {
        setSelected(null)
        cy.elements().removeClass('dimmed')
      }
    })

    cyRef.current = cy
  }

  const clearSelection = () => {
    setSelected(null)
    cyRef.current?.elements().removeClass('dimmed')
  }

  const toggleType = type => setTypes(prev => prev.map(t => t.type === type ? { ...t, visible: !t.visible } : t))

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Left sidebar ── */}
      <aside className="w-56 flex-shrink-0 flex flex-col border-r border-border bg-surface overflow-y-auto">

        {/* Controls */}
        <div className="p-4 border-b border-border space-y-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-600">Load</p>
          <div>
            <label className="text-[11px] text-slate-500 block mb-1">Max nodes</label>
            <input
              type="number" value={limit} min={10} max={2000}
              onChange={e => setLimit(Number(e.target.value))}
              className="w-full bg-card border border-border rounded-lg px-2.5 py-1.5 text-xs text-slate-300 outline-none focus:border-accent/40"
            />
          </div>
          <div>
            <label className="text-[11px] text-slate-500 block mb-1">Search</label>
            <div className="relative">
              <Search size={11} className="absolute left-2.5 top-2 text-slate-600" />
              <input
                type="text" value={search} placeholder="Filter by name…"
                onChange={e => setSearch(e.target.value)}
                className="w-full bg-card border border-border rounded-lg pl-7 pr-2.5 py-1.5 text-xs text-slate-300 outline-none focus:border-accent/40"
              />
            </div>
          </div>
          <button
            onClick={loadGraph} disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-accent hover:bg-accent-2 disabled:opacity-50 text-white text-xs font-semibold rounded-lg py-2 transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Loading…' : loaded ? 'Reload' : 'Load Graph'}
          </button>
        </div>

        {/* Stats */}
        {stats && (
          <div className="p-4 border-b border-border">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-600 mb-2">Stats</p>
            <div className="space-y-1">
              {[['Nodes', stats.nodes], ['Edges', stats.edges]].map(([k, v]) => (
                <div key={k} className="flex justify-between text-xs">
                  <span className="text-slate-600">{k}</span>
                  <span className="text-slate-300 font-medium">{v}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Type filter */}
        {types.length > 0 && (
          <div className="p-4 border-b border-border">
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-600 mb-2">Entity types</p>
            <div className="space-y-2">
              {types.map(t => (
                <button
                  key={t.type}
                  onClick={() => toggleType(t.type)}
                  className="w-full flex items-center gap-2 text-left group"
                >
                  <span className={`w-2.5 h-2.5 rounded-sm flex-shrink-0 transition-opacity ${t.visible ? 'opacity-100' : 'opacity-25'}`}
                    style={{ backgroundColor: t.color }} />
                  <span className={`text-[11px] flex-1 truncate transition-colors ${t.visible ? 'text-slate-400' : 'text-slate-700'}`}>
                    {t.type}
                  </span>
                  <span className="text-[10px] text-slate-700">{t.count}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Selected node */}
        {selected && (
          <div className="p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-600">Selected</p>
              <button onClick={clearSelection} className="text-slate-700 hover:text-slate-500 transition-colors">
                <X size={12} />
              </button>
            </div>
            <div className="space-y-2">
              <div className="flex items-start gap-2">
                <span className="w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0" style={{ backgroundColor: selected.color }} />
                <span className="text-sm font-medium text-slate-200 leading-tight break-words">{selected.name}</span>
              </div>
              <div>
                <span className="text-[10px] px-2 py-0.5 rounded-full border"
                  style={{ backgroundColor: selected.color + '15', borderColor: selected.color + '40', color: selected.color }}>
                  {selected.type}
                </span>
              </div>
              <p className="text-[10px] text-slate-700">Degree: {selected.degree}</p>
              {selected.neighbors.length > 0 && (
                <div>
                  <p className="text-[10px] text-slate-600 mb-1">Neighbors</p>
                  <div className="space-y-0.5 max-h-36 overflow-y-auto">
                    {selected.neighbors.slice(0, 20).map((n, i) => (
                      <p key={i} className="text-[10px] text-slate-500 truncate">{n.name}</p>
                    ))}
                    {selected.neighbors.length > 20 && (
                      <p className="text-[10px] text-slate-700">+{selected.neighbors.length - 20} more</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </aside>

      {/* ── Canvas ── */}
      <div className="flex-1 relative bg-base">
        {!loaded && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center space-y-2">
              <div
                className="text-4xl font-black opacity-10 select-none"
                style={{ background: 'linear-gradient(135deg,#7c5cfc,#c084fc)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
              >◈</div>
              <p className="text-sm text-slate-600">{status}</p>
            </div>
          </div>
        )}
        <div ref={containerRef} className="absolute inset-0" id="cy" />

        {/* Legend overlay */}
        {types.length > 0 && (
          <div className="absolute bottom-4 right-4 bg-base/90 backdrop-blur border border-border rounded-xl px-3 py-2.5 pointer-events-none">
            <div className="flex flex-wrap gap-x-3 gap-y-1.5 max-w-xs">
              {types.filter(t => t.visible).map(t => (
                <div key={t.type} className="flex items-center gap-1.5 text-[10px] text-slate-500">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: t.color }} />
                  {t.type}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Cytoscape style ──────────────────────────────────────────────────────────

function cytoscapeStyle() {
  return [
    {
      selector: 'node',
      style: {
        'background-color':   'data(color)',
        'label':              'data(label)',
        'color':              '#94a3b8',
        'font-size':          9,
        'font-family':        'Inter, system-ui, sans-serif',
        'text-valign':        'bottom',
        'text-margin-y':      4,
        'text-outline-color': '#090b18',
        'text-outline-width': 2,
        'width':              24,
        'height':             24,
        'border-width':       1.5,
        'border-color':       'rgba(255,255,255,0.1)',
        'transition-property':'opacity, width, height',
        'transition-duration':'0.15s',
      },
    },
    {
      selector: 'node:selected',
      style: {
        'border-width': 3,
        'border-color': '#ffffff',
        'width':  32,
        'height': 32,
      },
    },
    {
      selector: 'node.search-match',
      style: {
        'border-width': 3,
        'border-color': '#fbbf24',
        'width':  32,
        'height': 32,
      },
    },
    {
      selector: 'node.dimmed',
      style: { 'opacity': 0.1 },
    },
    {
      selector: 'node.hidden-type',
      style: { 'display': 'none' },
    },
    {
      selector: 'edge',
      style: {
        'width':               1.2,
        'line-color':          'rgba(80,90,130,0.5)',
        'target-arrow-color':  'rgba(80,90,130,0.6)',
        'target-arrow-shape':  'triangle',
        'curve-style':         'bezier',
        'label':               'data(label)',
        'font-size':           7,
        'color':               'rgba(90,100,130,0.7)',
        'font-family':         'Inter, system-ui, sans-serif',
        'text-rotation':       'autorotate',
        'text-outline-color':  '#090b18',
        'text-outline-width':  1.5,
        'transition-property': 'opacity',
        'transition-duration': '0.15s',
      },
    },
    {
      selector: 'edge.dimmed',
      style: { 'opacity': 0.05 },
    },
  ]
}
