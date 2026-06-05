import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Bug } from 'lucide-react'
import DebugTrace from '../components/DebugTrace'

// ── Chat page ───────────────────────────────────────────────────────────────

export default function ChatPage({ apiUrl }) {
  const [messages, setMessages] = useState([])
  const [input, setInput]       = useState('')
  const [streaming, setStreaming] = useState(false)
  const [debugMode, setDebugMode] = useState(false)
  const endRef     = useRef(null)
  const textareaRef = useRef(null)

  // Scroll to bottom on new content
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-resize textarea
  const resizeTextarea = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 180) + 'px'
  }

  const send = useCallback(async () => {
    const q = input.trim()
    if (!q || streaming) return

    setInput('')
    setStreaming(true)
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    const userId   = Date.now()
    const assistId = userId + 1

    setMessages(prev => [
      ...prev,
      { id: userId,   role: 'user',      content: q },
      { id: assistId, role: 'assistant', content: '', steps: [], debug: debugMode, done: false, error: false },
    ])

    try {
      const res = await fetch(`${apiUrl}/chat`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ query: q, debug: debugMode }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })

        if (debugMode) {
          buf += chunk
          const parts = buf.split('\n\n')
          buf = parts.pop() ?? ''

          for (const part of parts) {
            const line = part.startsWith('data: ') ? part.slice(6) : part
            try {
              const evt = JSON.parse(line)
              handleDebugEvent(evt, assistId)
            } catch { /* partial */ }
          }
        } else {
          setMessages(prev => patchLast(prev, assistId, m => ({ ...m, content: m.content + chunk })))
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        setMessages(prev => patchLast(prev, assistId, m => ({
          ...m, content: `Error: ${e.message}`, error: true, done: true,
        })))
      }
    } finally {
      setMessages(prev => patchLast(prev, assistId, m => ({ ...m, done: true })))
      setStreaming(false)
      textareaRef.current?.focus()
    }
  }, [input, streaming, debugMode, apiUrl])

  function handleDebugEvent(evt, id) {
    if (evt.t === 'step') {
      setMessages(prev => patchLast(prev, id, m => ({
        ...m,
        steps: [...m.steps.filter(s => s.step !== evt.step), evt],
      })))
    } else if (evt.t === 'token') {
      setMessages(prev => patchLast(prev, id, m => ({ ...m, content: m.content + evt.content })))
    } else if (evt.t === 'error') {
      setMessages(prev => patchLast(prev, id, m => ({
        ...m, content: `Pipeline error: ${evt.message}`, error: true,
      })))
    }
  }

  const handleKey = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div className="flex flex-col h-full">
      {/* ── Header ── */}
      <header className="flex items-center justify-between px-8 py-5 border-b border-border flex-shrink-0">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">Ask Lattice</h1>
          <p className="text-xs text-slate-500 mt-0.5">Query your knowledge graph with natural language</p>
        </div>
        <DebugToggle value={debugMode} onChange={setDebugMode} />
      </header>

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {messages.length === 0 && <EmptyState />}
        {messages.map(msg =>
          msg.role === 'user'
            ? <UserMessage key={msg.id} msg={msg} />
            : <AssistantMessage key={msg.id} msg={msg} />
        )}
        <div ref={endRef} />
      </div>

      {/* ── Input bar ── */}
      <div className="flex-shrink-0 px-6 pb-6 pt-2">
        <div className="
          flex items-end gap-3
          bg-card border border-border rounded-2xl px-4 py-3
          focus-within:border-accent/40 transition-colors duration-150
        ">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => { setInput(e.target.value); resizeTextarea() }}
            onKeyDown={handleKey}
            placeholder="Ask anything about your data…"
            rows={1}
            disabled={streaming}
            className="
              flex-1 bg-transparent resize-none outline-none
              text-sm text-slate-200 placeholder-slate-600
              min-h-[22px] max-h-[180px] leading-relaxed disabled:opacity-60
            "
          />
          <button
            onClick={send}
            disabled={!input.trim() || streaming}
            className="
              flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
              bg-accent hover:bg-accent-2 disabled:opacity-40 disabled:cursor-not-allowed
              transition-all duration-150
            "
          >
            <Send size={13} className="text-white" />
          </button>
        </div>
        <p className="text-[11px] text-slate-700 text-center mt-2">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function patchLast(msgs, id, fn) {
  return msgs.map(m => m.id === id ? fn(m) : m)
}

// ── Sub-components ───────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-center py-20">
      <div
        className="text-5xl font-black opacity-10 select-none"
        style={{ background: 'linear-gradient(135deg,#7c5cfc,#c084fc)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}
      >◈</div>
      <p className="text-sm text-slate-600">Ask anything about your ingested data</p>
    </div>
  )
}

function UserMessage({ msg }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-xl bg-accent/20 border border-accent/25 rounded-2xl rounded-br-md px-4 py-3 text-sm text-slate-200 msg-text">
        {msg.content}
      </div>
    </div>
  )
}

function AssistantMessage({ msg }) {
  return (
    <div className="flex flex-col gap-3 max-w-3xl">
      {/* Debug trace — shown before answer */}
      {msg.debug && msg.steps.length > 0 && (
        <DebugTrace steps={msg.steps} />
      )}
      {/* Answer bubble */}
      <div className={`
        bg-card border rounded-2xl rounded-bl-md px-4 py-3 text-sm
        ${msg.error ? 'border-red-500/30 text-red-400' : 'border-border text-slate-200'}
      `}>
        {msg.content
          ? <span className="msg-text">{msg.content}</span>
          : <TypingDots />
        }
      </div>
    </div>
  )
}

function TypingDots() {
  return (
    <span className="flex items-center gap-1.5 py-0.5">
      <span className="w-1.5 h-1.5 rounded-full bg-slate-500 dot-1" />
      <span className="w-1.5 h-1.5 rounded-full bg-slate-500 dot-2" />
      <span className="w-1.5 h-1.5 rounded-full bg-slate-500 dot-3" />
    </span>
  )
}

function DebugToggle({ value, onChange }) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer select-none">
      <Bug size={14} className={value ? 'text-accent-2' : 'text-slate-600'} />
      <span className={`text-xs font-medium ${value ? 'text-accent-2' : 'text-slate-500'}`}>Debug</span>
      <button
        role="switch"
        aria-checked={value}
        onClick={() => onChange(v => !v)}
        className={`relative w-9 h-5 rounded-full transition-colors duration-200 ${value ? 'bg-accent' : 'bg-slate-700'}`}
      >
        <span
          className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${value ? 'translate-x-4' : 'translate-x-0.5'}`}
        />
      </button>
    </label>
  )
}
