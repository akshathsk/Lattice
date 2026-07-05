import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import HomePage from './pages/HomePage'
import ChatPage from './pages/ChatPage'
import GraphPage from './pages/GraphPage'
import ConnectorsPage from './pages/ConnectorsPage'

export default function App() {
  const [page, setPage] = useState('home')
  const [apiUrl, setApiUrl] = useState('http://localhost:8000')
  const [health, setHealth] = useState('checking') // 'ok' | 'error' | 'checking'

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      if (cancelled) return
      setHealth('checking')
      try {
        const res = await fetch(`${apiUrl}/health`, { signal: AbortSignal.timeout(4000) })
        if (!cancelled) setHealth(res.ok ? 'ok' : 'error')
      } catch {
        if (!cancelled) setHealth('error')
      }
    }
    check()
    const id = setInterval(check, 30_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [apiUrl])

  return (
    <div className="flex h-full bg-base text-slate-200 overflow-hidden">
      <Sidebar page={page} setPage={setPage} apiUrl={apiUrl} setApiUrl={setApiUrl} health={health} />
      <main className="flex-1 overflow-hidden flex flex-col">
        {page === 'home'       && <HomePage       apiUrl={apiUrl} setPage={setPage} />}
        {page === 'chat'       && <ChatPage       apiUrl={apiUrl} />}
        {page === 'graph'      && <GraphPage      apiUrl={apiUrl} />}
        {page === 'connectors' && <ConnectorsPage apiUrl={apiUrl} setPage={setPage} />}
      </main>
    </div>
  )
}
