/* ── Lattice frontend ─────────────────────────────────────────────────────── */

// ── State ─────────────────────────────────────────────────────────────────

let debugMode = false;
let streaming  = false;

const apiUrl = () => document.getElementById('api-url').value.replace(/\/$/, '');

// ── Navigation ────────────────────────────────────────────────────────────

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.page;
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('page-' + target).classList.add('active');

    // Lazy-load Cytoscape when graph page opens for the first time
    if (target === 'graph') {
      window._loadCytoscape(() => { /* ready */ });
    }
  });
});

// ── Health check ──────────────────────────────────────────────────────────

async function checkHealth() {
  const dot = document.getElementById('health-dot');
  dot.className = 'health-dot';
  dot.title = 'Checking…';
  try {
    const res = await fetch(apiUrl() + '/health', { signal: AbortSignal.timeout(4000) });
    if (res.ok) {
      dot.classList.add('ok');
      dot.title = 'API reachable';
    } else {
      dot.classList.add('err');
      dot.title = 'API returned ' + res.status;
    }
  } catch {
    dot.classList.add('err');
    dot.title = 'Cannot reach API';
  }
}

let healthTimer;
document.getElementById('api-url').addEventListener('input', () => {
  clearTimeout(healthTimer);
  healthTimer = setTimeout(checkHealth, 700);
});
checkHealth();
setInterval(checkHealth, 30_000);

// ── Debug toggle ──────────────────────────────────────────────────────────

document.getElementById('debug-checkbox').addEventListener('change', function () {
  debugMode = this.checked;
});

// ── Chat ──────────────────────────────────────────────────────────────────

const messagesEl = document.getElementById('messages');
const chatInput  = document.getElementById('chat-input');
const sendBtn    = document.getElementById('send-btn');

// Auto-grow textarea
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 180) + 'px';
});

// Enter = send, Shift+Enter = newline
chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
sendBtn.addEventListener('click', sendMessage);

// ── Message helpers ───────────────────────────────────────────────────────

function clearEmpty() {
  const es = document.getElementById('empty-state');
  if (es) es.remove();
}

/**
 * Append a message row and return { bubble, traceEl }.
 * traceEl is only set for assistant messages when debug=true.
 */
function appendMessage(role, text = '', withTrace = false) {
  clearEmpty();
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'user' ? '🧑' : '◈';

  const content = document.createElement('div');
  content.className = 'msg-content';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  content.appendChild(bubble);

  let traceEl = null;
  if (withTrace) {
    traceEl = document.createElement('div');
    traceEl.className = 'debug-trace';
    content.appendChild(traceEl);
  }

  row.appendChild(avatar);
  row.appendChild(content);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return { bubble, traceEl };
}

function showTypingIndicator() {
  clearEmpty();
  const row = document.createElement('div');
  row.className = 'msg-row assistant';
  row.id = 'typing-indicator';

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = '◈';

  const content = document.createElement('div');
  content.className = 'msg-content';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  content.appendChild(bubble);

  row.appendChild(avatar);
  row.appendChild(content);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return row;
}

// ── Send ──────────────────────────────────────────────────────────────────

async function sendMessage() {
  const query = chatInput.value.trim();
  if (!query || streaming) return;

  streaming = true;
  sendBtn.disabled = true;
  chatInput.disabled = true;

  appendMessage('user', query);
  chatInput.value = '';
  chatInput.style.height = 'auto';

  const indicator = showTypingIndicator();

  try {
    const res = await fetch(apiUrl() + '/chat', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ query, debug: debugMode }),
    });

    if (!res.ok) {
      indicator.remove();
      appendMessage('assistant', `Error ${res.status}: ${await res.text()}`);
      return;
    }

    indicator.remove();
    const { bubble, traceEl } = appendMessage('assistant', '', debugMode);

    if (debugMode) {
      await streamDebug(res, bubble, traceEl);
    } else {
      await streamRaw(res, bubble);
    }

  } catch (err) {
    const ind = document.getElementById('typing-indicator');
    if (ind) ind.remove();
    appendMessage('assistant', '[Connection error: ' + err.message + ']');
  } finally {
    streaming = false;
    sendBtn.disabled = false;
    chatInput.disabled = false;
    chatInput.focus();
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
}

// ── Plain text streaming ──────────────────────────────────────────────────

async function streamRaw(res, bubble) {
  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let text = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    text += decoder.decode(value, { stream: true });
    bubble.textContent = text;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  const tail = decoder.decode();
  if (tail) { text += tail; bubble.textContent = text; }
}

// ── Debug SSE streaming ───────────────────────────────────────────────────

async function streamDebug(res, bubble, traceEl) {
  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const steps = [];

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Split on double-newlines (SSE event boundaries)
    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const raw  = buffer.slice(0, boundary).trim();
      buffer     = buffer.slice(boundary + 2);

      if (!raw.startsWith('data: ')) continue;
      let evt;
      try { evt = JSON.parse(raw.slice(6)); } catch { continue; }

      if (evt.t === 'token') {
        bubble.textContent += evt.content;
        messagesEl.scrollTop = messagesEl.scrollHeight;
      } else if (evt.t === 'step') {
        steps.push(evt);
        renderDebugTrace(steps, traceEl);
      } else if (evt.t === 'error') {
        bubble.textContent += '\n\n[Pipeline error: ' + evt.message + ']';
      }
      // 'done' event — nothing to do, loop exits naturally
    }
  }
}

// ── Debug trace rendering ─────────────────────────────────────────────────

function renderDebugTrace(steps, container) {
  // Preserve expanded/collapsed state by keying on step name
  const openSteps = new Set(
    [...container.querySelectorAll('.debug-step-body.open')]
      .map(el => el.dataset.step)
  );

  container.innerHTML = '';
  for (const step of steps) {
    const card = buildStepCard(step);
    // Restore open state
    if (openSteps.has(step.step)) {
      card.querySelector('.debug-step-body').classList.add('open');
      const chev = card.querySelector('.step-chevron');
      if (chev) chev.classList.add('open');
    }
    container.appendChild(card);
  }
}

function buildStepCard(step) {
  const card = document.createElement('div');
  card.className = 'debug-step';

  let summary = '';
  let body = '';

  if (step.step === 'retrieval') {
    const d = step.detail;
    summary = `Path A: ${d.path_a_chunks} chunks  •  Entities: ${d.path_b_entities}  •  Ranked: ${d.total_ranked}`;
    body = buildRetrievalBody(step);
  } else if (step.step === 'graph') {
    const d = step.detail;
    summary = `${d.anchors} anchors  •  ${d.nodes} nodes  •  ${d.edges} edges`;
    body = buildGraphBody(step);
  } else if (step.step === 'prompt') {
    const d = step.detail;
    summary = `${esc(d.model)}  •  ${d.messages} messages`;
    body = buildPromptBody(step);
  }

  card.innerHTML = `
    <div class="debug-step-header">
      <div class="step-icon"></div>
      <div class="step-title">${esc(step.label)}</div>
      <div class="step-summary">${summary}</div>
      <div class="step-chevron">▼</div>
    </div>
    <div class="debug-step-body" data-step="${esc(step.step)}">
      ${body}
    </div>
  `;

  card.querySelector('.debug-step-header').addEventListener('click', () => {
    const bodyEl = card.querySelector('.debug-step-body');
    const chev   = card.querySelector('.step-chevron');
    bodyEl.classList.toggle('open');
    chev.classList.toggle('open');
  });

  return card;
}

function buildRetrievalBody(step) {
  const d = step.detail;
  const entityPills = (step.entities || []).map(e =>
    `<span class="entity-pill">
       ${esc(e.name)}
       <span class="pill-type">${esc(e.type)}</span>
       <span class="pill-dist">d=${e.dist}</span>
     </span>`
  ).join('');

  const chunkRows = (step.chunks || []).map((c, i) => {
    const viaBadges = c.via.map(v =>
      `<span class="via-badge ${v}">${v}</span>`
    ).join('');
    return `
      <div class="chunk-row">
        <div class="chunk-row-header">
          <span class="chunk-source">${esc(c.collection)}#${esc(c.record_id)}</span>
          <span class="chunk-score">↑${c.score.toFixed(3)}</span>
          <span class="chunk-via">${viaBadges}</span>
        </div>
        <div class="chunk-preview">${esc(c.preview)}</div>
      </div>
    `;
  }).join('');

  return `
    <div class="debug-kv" style="margin-top:10px">
      <span class="debug-kv-key">embedding dim</span>
      <span class="debug-kv-val">${d.embedding_dim}</span>
      <span class="debug-kv-key">Path A chunks</span>
      <span class="debug-kv-val">${d.path_a_chunks}</span>
      <span class="debug-kv-key">Path B entities</span>
      <span class="debug-kv-val">${d.path_b_entities}</span>
      <span class="debug-kv-key">Path B chunks</span>
      <span class="debug-kv-val">${d.path_b_chunks}</span>
      <span class="debug-kv-key">Boosted (both)</span>
      <span class="debug-kv-val">${d.boosted_chunks}</span>
      <span class="debug-kv-key">Total ranked</span>
      <span class="debug-kv-val">${d.total_ranked}</span>
    </div>
    ${step.entities?.length ? `
    <div class="debug-sub">
      <div class="debug-sub-title">Matched entities (Path B anchors)</div>
      <div class="entity-pills">${entityPills}</div>
    </div>` : ''}
    ${step.chunks?.length ? `
    <div class="debug-sub">
      <div class="debug-sub-title">Top ranked chunks</div>
      <div class="chunk-list">${chunkRows}</div>
    </div>` : ''}
  `;
}

function buildGraphBody(step) {
  const d = step.detail;
  const edgeRows = (step.edges || []).map(e =>
    `<div class="edge-row">
       (${esc(e.src)}) <span class="er">-[${esc(e.rel)}]-></span> (${esc(e.dst)})
     </div>`
  ).join('');

  return `
    <div class="debug-kv" style="margin-top:10px">
      <span class="debug-kv-key">anchors</span>
      <span class="debug-kv-val">${d.anchors} entities</span>
      <span class="debug-kv-key">traversal</span>
      <span class="debug-kv-val">${d.hops}-hop</span>
      <span class="debug-kv-key">subgraph nodes</span>
      <span class="debug-kv-val">${d.nodes}</span>
      <span class="debug-kv-key">subgraph edges</span>
      <span class="debug-kv-val">${d.edges}</span>
    </div>
    ${step.edges?.length ? `
    <div class="debug-sub">
      <div class="debug-sub-title">Relationships (up to 40 shown)</div>
      <div class="edge-list">${edgeRows}</div>
    </div>` : ''}
  `;
}

function buildPromptBody(step) {
  const msgs = (step.messages || []).map(m => {
    const chars = m.content.length;
    const id = 'pm-' + Math.random().toString(36).slice(2);
    return `
      <div class="prompt-msg">
        <div class="prompt-msg-header" onclick="
          this.nextElementSibling.classList.toggle('open')
        ">
          <span class="prompt-msg-role">${esc(m.role)}</span>
          <span class="prompt-msg-len">${chars.toLocaleString()} chars</span>
        </div>
        <div class="prompt-msg-body">${esc(m.content)}</div>
      </div>
    `;
  }).join('');

  return `
    <div class="debug-kv" style="margin-top:10px">
      <span class="debug-kv-key">model</span>
      <span class="debug-kv-val">${esc(step.detail.model)}</span>
      <span class="debug-kv-key">messages</span>
      <span class="debug-kv-val">${step.detail.messages}</span>
    </div>
    <div class="debug-sub">
      <div class="debug-sub-title">Messages (click to expand)</div>
      <div class="prompt-messages">${msgs}</div>
    </div>
  `;
}

// ── Graph visualization ───────────────────────────────────────────────────

let cy = null;   // Cytoscape instance

async function loadGraph() {
  const limit  = parseInt(document.getElementById('g-limit').value) || 300;
  const btn    = document.getElementById('g-load-btn');
  const emptyEl = document.getElementById('g-empty');

  btn.disabled = true;
  btn.textContent = 'Loading…';
  emptyEl.textContent = 'Fetching graph data…';
  emptyEl.style.display = 'flex';

  try {
    const res = await fetch(apiUrl() + '/graph/data?limit=' + limit);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();

    if (!data.nodes?.length) {
      emptyEl.textContent = 'No entities found — run an ingest first.';
      return;
    }

    emptyEl.style.display = 'none';
    window._loadCytoscape(() => renderGraph(data.nodes, data.edges || []));
    renderGraphStats(data.nodes, data.edges || []);
    renderTypeFilters(data.nodes);
    renderLegend(data.nodes);

    document.getElementById('g-stats-section').style.display = '';
    document.getElementById('g-filter-section').style.display = '';
    document.getElementById('g-legend').style.display = 'flex';

  } catch (err) {
    emptyEl.textContent = 'Failed to load graph: ' + err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Reload Graph';
  }
}

function renderGraph(nodes, edges) {
  const nodeSet = new Set(nodes.map(n => n.id));
  const elements = [];

  for (const n of nodes) {
    elements.push({
      data: {
        id:       n.id,
        label:    n.name.length > 22 ? n.name.slice(0, 20) + '…' : n.name,
        fullName: n.name,
        type:     n.type,
        color:    typeColor(n.type),
      },
    });
  }

  for (const e of edges) {
    // Only include edges where both endpoints are in our node set
    if (nodeSet.has(e.src) && nodeSet.has(e.dst)) {
      elements.push({
        data: {
          id:     `${e.src}-${e.type}-${e.dst}`,
          source: e.src,
          target: e.dst,
          label:  e.type,
        },
      });
    }
  }

  if (cy) cy.destroy();

  cy = cytoscape({
    container: document.getElementById('cy'),
    elements,
    style: graphStyle(),
    layout: {
      name:            'cose',
      animate:         nodes.length < 200,
      animationDuration: 400,
      nodeRepulsion:   8000,
      idealEdgeLength: 90,
      edgeElasticity:  0.5,
      gravity:         0.25,
      numIter:         nodes.length < 200 ? 1000 : 400,
      initialTemp:     1000,
      coolingFactor:   0.99,
      minTemp:         1.0,
    },
    minZoom: 0.05,
    maxZoom: 5,
  });

  // Click node → show detail
  cy.on('tap', 'node', evt => {
    showNodeDetail(evt.target.data());
    cy.nodes().removeClass('dimmed');
    cy.edges().removeClass('dimmed');
  });

  // Click background → clear selection
  cy.on('tap', evt => {
    if (evt.target === cy) {
      cy.nodes().removeClass('dimmed');
      cy.edges().removeClass('dimmed');
      document.getElementById('g-node-section').style.display = 'none';
    }
  });
}

function graphStyle() {
  return [
    {
      selector: 'node',
      style: {
        'background-color':  'data(color)',
        'label':             'data(label)',
        'color':             '#e8e9f0',
        'font-size':         '9px',
        'text-valign':       'center',
        'text-halign':       'center',
        'text-outline-color':'#0d0f1a',
        'text-outline-width': 2,
        'width':             26,
        'height':            26,
        'border-width':      1.5,
        'border-color':      'rgba(255,255,255,0.12)',
        'transition-property': 'opacity, border-width',
        'transition-duration': '0.15s',
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
      selector: 'edge',
      style: {
        'width':               1.5,
        'line-color':          'rgba(90,93,122,0.5)',
        'target-arrow-color':  'rgba(90,93,122,0.6)',
        'target-arrow-shape':  'triangle',
        'curve-style':         'bezier',
        'label':               'data(label)',
        'font-size':           '7px',
        'color':               'rgba(90,93,122,0.85)',
        'text-rotation':       'autorotate',
        'text-outline-color':  '#0d0f1a',
        'text-outline-width':  1.5,
        'transition-property': 'opacity',
        'transition-duration': '0.15s',
      },
    },
    {
      selector: '.dimmed',
      style: { 'opacity': 0.12 },
    },
    {
      selector: '.search-match',
      style: {
        'border-width': 3,
        'border-color': '#f5a623',
        'width':  34,
        'height': 34,
      },
    },
    {
      selector: '.hidden-type',
      style: { 'display': 'none' },
    },
  ];
}

// ── Graph sidebar: stats ──────────────────────────────────────────────────

function renderGraphStats(nodes, edges) {
  const typeCounts = {};
  for (const n of nodes) {
    typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;
  }

  const rows = Object.entries(typeCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => `
      <div class="g-stat-row">
        <span class="g-type-dot" style="background:${typeColor(type)}"></span>
        <span class="g-stat-type">${esc(type)}</span>
        <span class="g-stat-count">${count}</span>
      </div>
    `).join('');

  document.getElementById('g-stats-content').innerHTML = `
    <div class="g-stat-totals">
      <span>${nodes.length}</span> nodes &nbsp;
      <span>${edges.length}</span> edges
    </div>
    ${rows}
  `;
}

// ── Graph sidebar: type filter ────────────────────────────────────────────

function renderTypeFilters(nodes) {
  const typeCounts = {};
  for (const n of nodes) typeCounts[n.type] = (typeCounts[n.type] || 0) + 1;

  const container = document.getElementById('g-type-filters');
  container.innerHTML = '';

  for (const [type, count] of Object.entries(typeCounts).sort()) {
    const label = document.createElement('label');
    label.className = 'g-filter-item';
    label.innerHTML = `
      <input type="checkbox" checked value="${esc(type)}" />
      <span class="g-type-dot" style="background:${typeColor(type)}"></span>
      ${esc(type)}
      <span class="g-count">${count}</span>
    `;
    label.querySelector('input').addEventListener('change', applyTypeFilter);
    container.appendChild(label);
  }
}

function applyTypeFilter() {
  if (!cy) return;
  const shown = new Set(
    [...document.querySelectorAll('#g-type-filters input:checked')].map(cb => cb.value)
  );
  cy.nodes().forEach(n => {
    if (shown.has(n.data('type'))) n.removeClass('hidden-type');
    else                           n.addClass('hidden-type');
  });
}

// ── Graph sidebar: selected node ──────────────────────────────────────────

function showNodeDetail(data) {
  const section = document.getElementById('g-node-section');
  const content = document.getElementById('g-node-content');
  section.style.display = '';

  const color = typeColor(data.type);
  content.innerHTML = `
    <div class="node-detail-name">${esc(data.fullName)}</div>
    <div class="node-detail-type">
      <span class="type-badge"
        style="background:${color}20;color:${color};border-color:${color}50">
        ${esc(data.type)}
      </span>
    </div>
    <div class="node-detail-props" style="margin-top:6px;font-size:11px;color:var(--text-muted)">
      ID: <code style="font-size:10px">${esc(data.id.slice(0, 16))}…</code>
    </div>
  `;
}

// ── Graph legend ──────────────────────────────────────────────────────────

function renderLegend(nodes) {
  const types = [...new Set(nodes.map(n => n.type))].sort();
  const legendEl = document.getElementById('g-legend');
  legendEl.innerHTML = types.map(t => `
    <div class="legend-item">
      <span class="g-type-dot" style="background:${typeColor(t)}"></span>
      ${esc(t)}
    </div>
  `).join('');
}

// ── Graph search ──────────────────────────────────────────────────────────

document.getElementById('g-search').addEventListener('input', function () {
  if (!cy) return;
  const q = this.value.toLowerCase().trim();

  cy.nodes().removeClass('dimmed search-match');
  cy.edges().removeClass('dimmed');

  if (!q) return;

  const matches = cy.nodes().filter(n =>
    n.data('fullName').toLowerCase().includes(q)
  );
  const nonMatches = cy.nodes().not(matches);

  if (matches.length) {
    matches.addClass('search-match');
    nonMatches.addClass('dimmed');
    // Dim edges whose both endpoints are not matched
    cy.edges().forEach(edge => {
      const srcMatch = matches.has(cy.$id(edge.data('source')));
      const dstMatch = matches.has(cy.$id(edge.data('target')));
      if (!srcMatch && !dstMatch) edge.addClass('dimmed');
    });
  }
});

// ── Connectors: load defaults ─────────────────────────────────────────────

async function loadConnectorDefaults() {
  try {
    const res = await fetch(apiUrl() + '/connectors/defaults');
    if (!res.ok) return;
    const data = await res.json();

    const pg = data.postgres || {};
    const mg = data.mongo    || {};

    // Override with whatever the API says (env vars take priority over hardcoded HTML defaults)
    setVal('pg-host', pg.host);
    setVal('pg-port', pg.port);
    setVal('pg-db',   pg.database);
    setVal('pg-user', pg.user);
    // password is intentionally omitted from the defaults endpoint

    setVal('mg-host', mg.host);
    setVal('mg-port', mg.port);
    setVal('mg-db',   mg.database);
  } catch { /* silently fail — HTML defaults remain */ }
}

function setVal(id, value) {
  const el = document.getElementById(id);
  if (el && value != null) el.value = value;
}

loadConnectorDefaults();
document.getElementById('api-url').addEventListener('change', loadConnectorDefaults);

// ── Connectors: helpers ───────────────────────────────────────────────────

function val(id)    { return document.getElementById(id)?.value?.trim() || ''; }
function intVal(id) { const v = parseInt(val(id)); return isNaN(v) ? undefined : v; }
function csvArr(str){ return str.split(',').map(s => s.trim()).filter(Boolean); }

function getConnectorConfig(source) {
  if (source === 'postgres') return {
    host:     val('pg-host')  || undefined,
    port:     intVal('pg-port'),
    dbname:   val('pg-db')   || undefined,
    user:     val('pg-user') || undefined,
    password: val('pg-pass') || undefined,
  };
  if (source === 'mongo') return {
    host:     val('mg-host')  || undefined,
    port:     intVal('mg-port'),
    database: val('mg-db')   || undefined,
  };
}

function resultEl(src) {
  return document.getElementById(src === 'postgres' ? 'pg-result' : 'mg-result');
}

function showResult(src, ok, titleText, body) {
  const el = resultEl(src);
  el.className = 'result-box ' + (ok ? 'ok' : 'err');
  el.innerHTML = `
    <div class="result-title"><span>${ok ? '✓' : '✗'}</span> ${titleText}</div>
    ${body}
  `;
}

function cardBtns(src, disabled) {
  document.getElementById('card-' + src)
    .querySelectorAll('.btn')
    .forEach(b => b.disabled = disabled);
}

// ── Connectors: test ──────────────────────────────────────────────────────

async function testConnector(source) {
  cardBtns(source, true);
  resultEl(source).className = 'result-box';
  resultEl(source).innerHTML = '<span style="color:var(--text-muted)">Testing…</span>';

  try {
    const res = await fetch(apiUrl() + '/connectors/' + source + '/test', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(cleanObj(getConnectorConfig(source))),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.ok) {
      showResult(source, true, 'Connection successful', '');
    } else {
      showResult(source, false, 'Connection failed',
        `<div style="color:var(--text-secondary)">${data.detail || res.statusText}</div>`);
    }
  } catch (err) {
    showResult(source, false, 'Request failed',
      `<div style="color:var(--text-secondary)">${err.message}</div>`);
  } finally {
    cardBtns(source, false);
  }
}

// ── Connectors: ingest ────────────────────────────────────────────────────

async function runIngest(source) {
  cardBtns(source, true);

  const el = resultEl(source);
  el.className = 'result-box ingest-progress';
  el.innerHTML = `
    <div class="ingest-header">
      <span class="ingest-status-label">Starting ingest…</span>
      <span class="ingest-timer" id="${source}-timer">0s</span>
    </div>
    <div class="progress-bar-wrap">
      <div class="progress-bar-fill" id="${source}-bar" style="width:0%"></div>
    </div>
    <div class="ingest-counts" id="${source}-counts">
      Chunks <b>0</b> / <b>?</b> &nbsp;·&nbsp;
      Entities <b>0</b> &nbsp;·&nbsp;
      Relations <b>0</b>
    </div>
    <div class="ingest-current" id="${source}-current"></div>
    <div class="ingest-log"    id="${source}-log"></div>
  `;

  const body = { connection: cleanObj(getConnectorConfig(source)) };
  if (source === 'postgres') {
    const t = csvArr(val('pg-tables'));
    if (t.length) body.tables = t;
  }
  if (source === 'mongo') {
    const c = csvArr(val('mg-collections'));
    if (c.length) body.collections = c;
  }

  // Live timer
  const t0 = Date.now();
  const timerEl = document.getElementById(source + '-timer');
  const timerInterval = setInterval(() => {
    timerEl.textContent = ((Date.now() - t0) / 1000).toFixed(0) + 's';
  }, 500);

  try {
    const res = await fetch(apiUrl() + '/ingest/' + source, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });

    if (!res.ok) {
      const txt = await res.text();
      showResult(source, false, 'Ingest failed', `<div style="color:var(--text-secondary)">${esc(txt)}</div>`);
      return;
    }

    await streamIngestProgress(res, source, el);

  } catch (err) {
    showResult(source, false, 'Request failed',
      `<div style="color:var(--text-secondary)">${esc(err.message)}</div>`);
  } finally {
    clearInterval(timerInterval);
    cardBtns(source, false);
  }
}

async function streamIngestProgress(res, source, el) {
  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const barEl      = document.getElementById(source + '-bar');
  const countsEl   = document.getElementById(source + '-counts');
  const currentEl  = document.getElementById(source + '-current');
  const logEl      = document.getElementById(source + '-log');
  const statusEl   = el.querySelector('.ingest-status-label');

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const raw  = buffer.slice(0, boundary).trim();
      buffer     = buffer.slice(boundary + 2);
      if (!raw.startsWith('data: ')) continue;
      let evt;
      try { evt = JSON.parse(raw.slice(6)); } catch { continue; }

      if (evt.t === 'start') {
        statusEl.textContent = `Ingesting ${evt.total} chunks…`;
        countsEl.innerHTML   = `Chunks <b>0</b> / <b>${evt.total}</b> &nbsp;·&nbsp; Entities <b>0</b> &nbsp;·&nbsp; Relations <b>0</b>`;

      } else if (evt.t === 'progress') {
        const pct = Math.round((evt.current / evt.total) * 100);
        barEl.style.width = pct + '%';
        statusEl.textContent = `Ingesting ${evt.current} / ${evt.total} chunks…`;
        countsEl.innerHTML = `Chunks <b>${evt.ok_chunks}</b> / <b>${evt.total}</b> &nbsp;·&nbsp; Entities <b>${evt.total_entities}</b> &nbsp;·&nbsp; Relations <b>${evt.total_relations}</b>`;

        const statusIcon = evt.error ? '✗' : '✓';
        const statusClass = evt.error ? 'log-err' : 'log-ok';
        const detail = evt.error
          ? ` — ${esc(evt.error)}`
          : ` +${evt.entities}e  +${evt.relations}r`;
        const line = document.createElement('div');
        line.className = 'log-line ' + statusClass;
        line.innerHTML = `<span class="log-icon">${statusIcon}</span> ${esc(evt.collection)}#${esc(evt.record_id)}${detail}`;
        logEl.appendChild(line);
        logEl.scrollTop = logEl.scrollHeight;

      } else if (evt.t === 'reindex') {
        barEl.style.width = '100%';
        statusEl.textContent = 'Rebuilding vector indexes…';
        currentEl.textContent = '';

      } else if (evt.t === 'done') {
        barEl.style.width = '100%';
        el.className = 'result-box ok';
        el.innerHTML = `
          <div class="result-title"><span>✓</span> Ingest complete — ${evt.elapsed_s}s</div>
          <div class="stat-grid">
            <div class="stat"><div class="stat-value">${evt.ok_chunks}</div><div class="stat-label">Chunks</div></div>
            <div class="stat"><div class="stat-value">${evt.total_entities}</div><div class="stat-label">Entities</div></div>
            <div class="stat"><div class="stat-value">${evt.total_relations}</div><div class="stat-label">Relations</div></div>
            <div class="stat"><div class="stat-value">${evt.total_merged}</div><div class="stat-label">Merged</div></div>
            <div class="stat"><div class="stat-value">${evt.failed_chunks}</div><div class="stat-label">Failed</div></div>
            <div class="stat"><div class="stat-value">${evt.elapsed_s}s</div><div class="stat-label">Time</div></div>
          </div>
        `;
        return;

      } else if (evt.t === 'error') {
        showResult(source, false, 'Ingest error',
          `<div style="color:var(--text-secondary)">${esc(evt.message)}</div>`);
        return;
      }
    }
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────

/** Remove keys whose value is undefined or empty string. */
function cleanObj(obj) {
  return Object.fromEntries(
    Object.entries(obj || {}).filter(([, v]) => v !== undefined && v !== '')
  );
}

/** HTML-escape a string. */
function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Deterministic color from an entity type name.
 * Uses a simple hash to pick from a palette of 12 distinct hues.
 */
function typeColor(type) {
  const palette = [
    '#7c5cfc', // purple
    '#3ecf8e', // green
    '#f5a623', // amber
    '#ff5c7a', // pink
    '#5ce8ff', // cyan
    '#ff9a5c', // orange
    '#a8ff5c', // lime
    '#ff5ce8', // magenta
    '#5c9aff', // blue
    '#5cffc4', // teal
    '#ffd15c', // yellow
    '#c45cff', // violet
  ];
  let h = 0;
  for (let i = 0; i < (type || '').length; i++) {
    h = (h * 31 + type.charCodeAt(i)) & 0x0fffffff;
  }
  return palette[h % palette.length];
}
