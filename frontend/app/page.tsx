'use client'

import { useState, useRef, useEffect } from 'react'
import ReactMarkdown, { Components } from 'react-markdown'

const BACKEND = 'https://repochat-backend.onrender.com'

const STEPS = [
  { label: 'Cloning repository', icon: '⊗' },
  { label: 'Reading source files', icon: '⊗' },
  { label: 'Chunking code', icon: '↻' },
  { label: 'Generating embeddings', icon: '{}' },
  { label: 'Storing vectors', icon: '🗄' },
]

const SUGGESTED = [
  'How does database connection work?',
  'What is the main entry point?',
  'Explain the query execution flow.',
  'What dependencies does this use?',
]

// TypeScript Interfaces to fix VS Code errors
type Phase = 'landing' | 'loading' | 'chat'
type Source = { file_path: string; start_line: number; end_line: number }
type Message = { role: 'user' | 'assistant'; content: string; sources?: Source[] }
type RepoInfo = { files_processed: number; chunks_stored: number } | null

export default function Home() {
  const [phase, setPhase] = useState<Phase>('landing') 
  const [repoUrl, setRepoUrl] = useState('')
  const [repoId, setRepoId] = useState('')
  const [repoInfo, setRepoInfo] = useState<RepoInfo>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [loadingStep, setLoadingStep] = useState(0)
  const [isAsking, setIsAsking] = useState(false)
  const [error, setError] = useState('')
  // ─── ADDED THIS LINE ───
  const [isLargeRepo, setIsLargeRepo] = useState(false)
  const [ingestTime, setIngestTime] = useState<string | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const animateSteps = () => {
    let step = 0
    const interval = setInterval(() => {
      step++
      setLoadingStep(step)
      if (step >= STEPS.length) clearInterval(interval)
    }, 800)
    return interval
  }

const handleIngest = async (url = repoUrl) => {
    if (!url.trim()) return
    setRepoUrl(url)
    setError('')
    // ─── RESET WARNING STATE ───
    setIsLargeRepo(false)

    // ─── ADDED GITHUB API CHECK ───
    const match = url.match(/github\.com\/([^/]+)\/([^/]+)/)
    if (match) {
      try {
        const ghRes = await fetch(`https://api.github.com/repos/${match[1]}/${match[2]}`)
        if (ghRes.ok) {
          const ghData = await ghRes.json()
          // If repo is > 15MB, flip the warning state
          if (ghData.size > 15000) {
            setIsLargeRepo(true)
          }
        }
      } catch (e) { 
        console.log('GitHub API preliminary check failed, proceeding anyway.') 
      }
    }

    setPhase('loading')
    setLoadingStep(0)

    // ─── MODIFIED STEPPER ANIMATION ───
    let currentStep = 0
    const interval = setInterval(() => {
      currentStep++
      if (currentStep >= STEPS.length - 1) {
        clearInterval(interval)
        setLoadingStep(STEPS.length - 1) // Force lock on 4th step (spinning loader)
      } else {
        setLoadingStep(currentStep)
      }
    }, 800)

    try {
      const res = await fetch(`${BACKEND}/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: url }),
      })

      clearInterval(interval)

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Ingestion failed')
      }

      const data = await res.json()
      setRepoId(data.repo_id)
      setRepoInfo({ files_processed: data.files_processed, chunks_stored: data.chunks_stored })
      setIngestTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))

      // ─── FORCE COMPLETE GREEN MARKS ONCE BACKEND RESOLVES ───
      setLoadingStep(STEPS.length)

      const repoName = url.replace('https://github.com/', '')

      setTimeout(() => {
        setPhase('chat')
        setMessages([{
          role: 'assistant',
          content: `Hello! I've analyzed the [${repoName}](${url}) repository. Ask me anything about the codebase.\n\nWhat would you like to know?`,
          sources: []
        }])
      }, 600)
    } catch (err: any) {
      clearInterval(interval)
      setPhase('landing')
      setError(err.message)
    }
  }

  const handleChat = async (q = question) => {
    if (!q.trim() || isAsking) return
    const userMessage: Message = { role: 'user', content: q, sources: [] }
    setMessages(prev => [...prev, userMessage])
    setQuestion('')
    setIsAsking(true)

    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }))
      const res = await fetch(`${BACKEND}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_id: repoId, question: q, chat_history: history }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.answer, sources: data.sources || [] }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Something went wrong. Please try again.', sources: [] }])
    } finally {
      setIsAsking(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, action: () => void) => {
    if (e.key === 'Enter') action()
  }

  const repoName = repoUrl.replace('https://github.com/', '')

  // Custom components for ReactMarkdown to handle styling
  const markdownComponents: Components = {
    pre({ children }) { return <>{children}</> },
    code({ className, children, ...props }: any) {
      // Check if it's inline by looking for newlines or language classes
      const isInline = !className && !String(children).includes('\n');
      
      if (isInline) {
        return <code style={{ background: '#efedf5', padding: '2px 6px', borderRadius: 4, fontFamily: 'JetBrains Mono, monospace', fontSize: 13, color: '#006399' }} {...props}>{children}</code>
      }
      
      const fileName = className?.replace('language-', '') || 'code'
      return (
        <div className="code-block">
          <div className="code-block-header">
            <span>{fileName}</span>
            <button onClick={() => navigator.clipboard.writeText(String(children))} style={{ background: 'none', border: 'none', color: '#8892a4', cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
              Copy
            </button>
          </div>
          <pre><code {...props}>{children}</code></pre>
        </div>
      )
    },
    p({ children }) { return <div style={{ marginBottom: 8 }}>{children}</div> },
    strong({ children }) { return <strong style={{ fontWeight: 600, color: '#006399' }}>{children}</strong> },
    a({ href, children }) { return <a href={href} target="_blank" rel="noreferrer" style={{ color: '#006399', textDecoration: 'none', borderBottom: '1px solid rgba(0,99,153,0.3)' }}>{children}</a> },
    ul({ children }) { return <ul style={{ paddingLeft: 20, marginBottom: 8 }}>{children}</ul> },
    ol({ children }) { return <ol style={{ paddingLeft: 20, marginBottom: 8 }}>{children}</ol> },
  }

  return (
    <div className="bg-gradient">
    {/* ── LANDING ── */}
      {phase === 'landing' && (
        <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
          {/* Nav */}
          <nav style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between', 
            padding: '20px 40px',
            borderBottom: '1px solid rgba(191,199,210,0.3)',
            background: 'rgba(255,255,255,0.5)',
            backdropFilter: 'blur(10px)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                width: 40, height: 40, borderRadius: '10px',
                background: 'linear-gradient(135deg, #006399, #3ea9f5)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 4px 12px rgba(0,99,153,0.3)'
              }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <rect x="3" y="3" width="8" height="8" rx="2" fill="white" opacity="0.9"/>
                  <rect x="13" y="3" width="8" height="5" rx="2" fill="white" opacity="0.7"/>
                  <rect x="3" y="13" width="8" height="5" rx="2" fill="white" opacity="0.7"/>
                  <rect x="13" y="10" width="8" height="8" rx="2" fill="white" opacity="0.9"/>
                </svg>
              </div>
              <span className="display" style={{ fontSize: 20, fontWeight: 700, color: '#1b1b21' }}>RepoChat</span>
            </div>
            <a href="https://github.com" target="_blank" rel="noreferrer" style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#3f4851', textDecoration: 'none', fontSize: 14, fontWeight: 600 }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.379.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.164 22 16.418 22 12c0-5.523-4.477-10-10-10z"/></svg>
              GitHub
            </a>
          </nav>

          {/* Hero Centered */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 24px', textAlign: 'center' }}>
            
            <h1 className="display" style={{ fontSize: 'clamp(40px, 6vw, 72px)', fontWeight: 800, lineHeight: 1.15, letterSpacing: '-0.02em', color: '#1b1b21', marginBottom: 24, maxWidth: 700 }}>
              Ask anything about<br />
              <span style={{ background: 'linear-gradient(135deg, #006399, #684eaa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                any codebase
              </span>
            </h1>

            <p style={{ fontSize: 18, color: '#6f7882', marginBottom: 48, maxWidth: 520, lineHeight: 1.6 }}>
              Paste a GitHub repo URL. Get cited answers from the actual source code.
            </p>

            <div style={{ width: '100%', maxWidth: 640 }}>
              <div className="clay-input" style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: 'rgba(255,255,255,0.95)', borderRadius: '1.25rem',
                padding: '8px 8px 8px 20px', border: '1px solid rgba(191,199,210,0.5)',
                boxShadow: '0 8px 32px rgba(0,99,153,0.05), inset 2px 2px 6px rgba(0,0,0,0.02)'
              }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#bfc7d2" strokeWidth="2.5">
                  <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
                  <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
                </svg>
                <input
                  value={repoUrl}
                  onChange={e => setRepoUrl(e.target.value)}
                  onKeyDown={e => handleKeyDown(e, () => handleIngest())}
                  placeholder="https://github.com/owner/repo"
                  style={{
                    flex: 1, border: 'none', outline: 'none', background: 'transparent',
                    fontSize: 16, color: '#1b1b21', fontFamily: 'Hanken Grotesk, sans-serif'
                  }}
                />
                <button
                  onClick={() => handleIngest()}
                  className="clay-btn display"
                  style={{
                    background: 'linear-gradient(135deg, #006399, #0080c0)',
                    color: 'white', border: 'none', borderRadius: '1rem',
                    padding: '14px 28px', fontSize: 16, fontWeight: 700, cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: 8
                  }}
                >
                  Analyze
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M5 12h14M12 5l7 7-7 7"/>
                  </svg>
                </button>
              </div>

              {error && <p style={{ color: '#ba1a1a', fontSize: 14, marginTop: 12, textAlign: 'center', fontWeight: 500 }}>{error}</p>}

              <div style={{ marginTop: 24, fontSize: 14, color: '#6f7882', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <span style={{ fontWeight: 600 }}>Try:</span>
                {['kennethreitz/records', 'pallets/flask', 'fastapi/fastapi'].map((r, i) => (
                  <span key={r} style={{ display: 'flex', alignItems: 'center' }}>
                    <button onClick={() => handleIngest(`https://github.com/${r}`)} style={{ background: 'none', border: 'none', color: '#006399', cursor: 'pointer', fontSize: 14, fontWeight: 600, padding: 0 }}>{r}</button>
                    {i < 2 && <span style={{ color: '#bfc7d2', margin: '0 8px' }}>·</span>}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Minimal Footer */}
          <footer style={{ padding: '24px 40px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <span style={{ fontSize: 13, color: '#8892a4', fontWeight: 500 }}>© 2026 RepoChat AI. Built for developers.</span>
          </footer>
        </div>
      )}

      {/* ── LOADING ── */}
      {phase === 'loading' && (
        <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
          <nav style={{ padding: '20px 40px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                width: 40, height: 40, borderRadius: '10px',
                background: 'linear-gradient(135deg, #006399, #3ea9f5)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 4px 12px rgba(0,99,153,0.3)'
              }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <rect x="3" y="3" width="8" height="8" rx="2" fill="white" opacity="0.9"/>
                  <rect x="13" y="3" width="8" height="5" rx="2" fill="white" opacity="0.7"/>
                  <rect x="3" y="13" width="8" height="5" rx="2" fill="white" opacity="0.7"/>
                  <rect x="13" y="10" width="8" height="8" rx="2" fill="white" opacity="0.9"/>
                </svg>
              </div>
              <span className="display" style={{ fontSize: 20, fontWeight: 700, color: '#1b1b21' }}>RepoChat</span>
            </div>
          </nav>

          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
            <div className="clay-card" style={{ width: '100%', maxWidth: 520, padding: '48px 40px' }}>
              <div style={{ textAlign: 'center', marginBottom: 24 }}>
                <div style={{
                  width: 64, height: 64, borderRadius: '1rem', margin: '0 auto 20px',
                  background: '#efedf5',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: 'inset 2px 2px 4px rgba(255,255,255,0.9), inset -1px -1px 3px rgba(0,0,0,0.08)'
                }}>
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#006399" strokeWidth="1.5">
                    <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                    <path d="M8 12h8M8 16h4"/>
                  </svg>
                </div>
                <h2 className="display" style={{ fontSize: 22, fontWeight: 700, color: '#1b1b21', marginBottom: 12 }}>Initializing Analysis</h2>
                <div className="chip mono" style={{ fontSize: 13 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#bfc7d2" strokeWidth="2"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>
                  {repoUrl}
                </div>
              </div>

              <div style={{ margin: '32px 0', position: 'relative' }}>
                {STEPS.map((step, i) => {
                  const done = loadingStep > i
                  const active = loadingStep === i
                  const isLast = i === STEPS.length - 1

                  return (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 16, position: 'relative' }}>
                      {!isLast && (
                        <div style={{
                          position: 'absolute', left: 19, top: 40, width: 2, height: 24,
                          background: done ? '#3ea9f5' : '#e4e1e9', zIndex: 0
                        }} />
                      )}
                      
                      <div style={{
                        width: 40, height: 40, borderRadius: '50%', flexShrink: 0,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        zIndex: 1, position: 'relative', marginBottom: isLast ? 0 : 24,
                        background: done ? 'linear-gradient(135deg, #39b597, #006b56)' :
                                   active ? 'linear-gradient(135deg, #3ea9f5, #006399)' :
                                   '#efedf5',
                        boxShadow: done ? '0 2px 8px rgba(0,107,86,0.3)' :
                                  active ? '0 2px 8px rgba(0,99,153,0.3)' :
                                  'inset 1px 1px 3px rgba(255,255,255,0.9), inset -1px -1px 2px rgba(0,0,0,0.08)'
                      }}>
                        {done ? (
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3">
                            <path d="M20 6L9 17l-5-5"/>
                          </svg>
                        ) : active ? (
                          <svg className="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
                            <path d="M21 12a9 9 0 11-6.219-8.56"/>
                          </svg>
                        ) : (
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#bfc7d2' }} />
                        )}
                      </div>

                      <div style={{ paddingTop: 10 }}>
                        <span style={{
                          fontSize: 15, fontWeight: active ? 600 : 400,
                          color: done ? '#3f4851' : active ? '#006399' : '#bfc7d2'
                        }}>
                          {step.label}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center', paddingTop: 16, borderTop: '1px solid #efedf5' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={isLargeRepo ? '#d97706' : '#bfc7d2'} strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M12 6v6l4 2"/>
                </svg>
                <span style={{ fontSize: 13, color: isLargeRepo ? '#d97706' : '#bfc7d2', fontWeight: isLargeRepo ? 600 : 400 }}>
                  {isLargeRepo 
                    ? "Large repository detected. Local processing may take several minutes." 
                    : "This takes 30–90 seconds depending on repo size"}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── CHAT ── */}
      {phase === 'chat' && (
        <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#f5f2fa' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 16, padding: '0 24px',
            height: 64, background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(10px)',
            borderBottom: '1px solid rgba(191,199,210,0.3)', flexShrink: 0
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, color: '#bfc7d2', fontFamily: 'JetBrains Mono, monospace' }}>terminal</span>
              <span className="display" style={{ fontSize: 18, fontWeight: 700, color: '#006399' }}>RepoChat</span>
            </div>
            <div style={{ width: 1, height: 24, background: '#e4e1e9' }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#3f4851', fontSize: 14 }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
              </svg>
              {repoName}
            </div>
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
              {repoInfo && (
                <div className="chip" style={{ fontSize: 13 }}>
                  {repoInfo.files_processed} files · {repoInfo.chunks_stored} chunks
                </div>
              )}
              <button
                onClick={() => { setPhase('landing'); setMessages([]); setRepoUrl('') }}
                className="clay-btn display"
                style={{
                  background: 'linear-gradient(135deg, #006399, #0080c0)',
                  color: 'white', border: 'none', borderRadius: '0.75rem',
                  padding: '8px 16px', fontSize: 14, fontWeight: 600, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M12 5v14M5 12l7-7 7 7"/>
                </svg>
                New Repo
              </button>
              
              {/* Top Navbar Human Avatar */}
              <div style={{
                width: 36, height: 36, borderRadius: '50%',
                background: 'linear-gradient(135deg, #684eaa, #3ea9f5)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'white', boxShadow: '0 2px 8px rgba(104,78,170,0.3)'
              }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                  <circle cx="12" cy="7" r="4"></circle>
                </svg>
              </div>

            </div>
          </div>

          <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
            <div className="mobile-hide" style={{ width: 256, borderRight: '1px solid rgba(191,199,210,0.3)', padding: 16, overflowY: 'auto', background: 'rgba(255,255,255,0.5)', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="sidebar-card" style={{ padding: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#006399" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3M12 17h.01"/>
                  </svg>
                  <span className="display" style={{ fontSize: 14, fontWeight: 700, color: '#006399' }}>Suggested Questions</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {SUGGESTED.map(q => (
                    <button key={q} className="question-chip" onClick={() => handleChat(q)}>{q}</button>
                  ))}
                </div>
              </div>

              <div className="sidebar-card" style={{ padding: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#006399" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 16v-4M12 8h.01"/>
                  </svg>
                  <span className="display" style={{ fontSize: 14, fontWeight: 700, color: '#006399' }}>Session Info</span>
                </div>
                {[
                  { label: 'REPOSITORY', value: repoUrl, isLink: true },
                  { label: 'STATS', value: `${repoInfo?.files_processed ?? 0} files processed\n${repoInfo?.chunks_stored ?? 0} chunks stored` },
                  { label: 'INGESTED', value: `Today at ${ingestTime}` },
                ].map(({ label, value, isLink }) => (
                  <div key={label} style={{ marginBottom: 14 }}>
                    <p style={{ fontSize: 11, fontWeight: 600, color: '#bfc7d2', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</p>
                    {isLink ? (
                      <a href={value} target="_blank" rel="noreferrer" style={{ fontSize: 13, color: '#006399', textDecoration: 'none', wordBreak: 'break-all' }}>{value}</a>
                    ) : (
                      <p style={{ fontSize: 13, color: '#3f4851', whiteSpace: 'pre-line' }}>{value}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div className="mobile-chat-area" style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
                {messages.map((msg, i) => (
                  <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flexDirection: msg.role === 'user' ? 'row-reverse' : 'row', maxWidth: '80%' }}>
                      
                      {/* Modern AI Bot Avatar */}
                      {msg.role === 'assistant' && (
                        <div style={{
                          width: 36, height: 36, borderRadius: '10px', flexShrink: 0,
                          background: '#efedf5', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          boxShadow: 'inset 1px 1px 3px rgba(255,255,255,0.9), 0 1px 4px rgba(0,0,0,0.06)'
                        }}>
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#006399" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="3" y="7" width="18" height="14" rx="2" ry="2" />
                            <path d="M12 3v4" />
                            <path d="M8 3h8" />
                            <circle cx="9" cy="13" r="1" />
                            <circle cx="15" cy="13" r="1" />
                            <path d="M10 17h4" />
                          </svg>
                        </div>
                      )}
                      
                      <div className={msg.role === 'user' ? 'user-bubble' : 'assistant-bubble'} style={{ padding: '16px 20px', fontSize: 15, lineHeight: 1.6 }}>
                        {msg.role === 'assistant' ? (
                          <ReactMarkdown components={markdownComponents}>
                            {msg.content}
                          </ReactMarkdown>
                        ) : msg.content}
                      </div>

                      {/* Human User Avatar */}
                      {msg.role === 'user' && (
                        <div style={{
                          width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
                          background: 'linear-gradient(135deg, #684eaa, #3ea9f5)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          color: 'white', boxShadow: '0 2px 8px rgba(104,78,170,0.3)'
                        }}>
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                            <circle cx="12" cy="7" r="4"></circle>
                          </svg>
                        </div>
                      )}

                    </div>
                    {msg.sources && msg.sources.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12, paddingLeft: msg.role === 'assistant' ? 48 : 0 }}>
                        {Array.from(new Set(msg.sources.map(src => `${src.file_path.split('/').pop()}:${src.start_line}–${src.end_line}`))).map((uniqueSrc, j) => (
                          <span key={j} style={{ 
                            display: 'inline-flex', alignItems: 'center', padding: '4px 10px', 
                            borderRadius: '6px', fontSize: '12px', fontFamily: 'JetBrains Mono, monospace', 
                            background: '#efedf5', border: '1px solid #e4e1e9', color: '#3f4851' 
                          }}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#bfc7d2" strokeWidth="2" style={{marginRight: 4}}>
                              <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
                              <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
                            </svg>
                            {uniqueSrc}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                
                {/* Assistant Loading Bubble */}
                {isAsking && (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                    <div style={{ 
                      width: 36, height: 36, borderRadius: '10px', flexShrink: 0,
                      background: '#efedf5', display: 'flex', alignItems: 'center', justifyContent: 'center', 
                      boxShadow: 'inset 1px 1px 3px rgba(255,255,255,0.9), 0 1px 4px rgba(0,0,0,0.06)' 
                    }}>
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#006399" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="7" width="18" height="14" rx="2" ry="2" />
                        <path d="M12 3v4" />
                        <path d="M8 3h8" />
                        <circle cx="9" cy="13" r="1" />
                        <circle cx="15" cy="13" r="1" />
                        <path d="M10 17h4" />
                      </svg>
                    </div>
                    <div className="assistant-bubble" style={{ padding: '16px 20px' }}>
                      <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                        {[0, 150, 300].map(d => (
                          <div key={d} style={{ width: 6, height: 6, borderRadius: '50%', background: '#bfc7d2', animation: `bounce 1s ease-in-out ${d}ms infinite` }} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              <div style={{ padding: '12px 24px 8px', background: 'rgba(255,255,255,0.8)', backdropFilter: 'blur(10px)', borderTop: '1px solid rgba(191,199,210,0.3)' }}>
                <div className="clay-input" style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  background: 'rgba(255,255,255,0.9)', borderRadius: '1rem', padding: '8px 8px 8px 20px',
                  border: '1px solid rgba(191,199,210,0.4)'
                }}>
                  <input
                    value={question}
                    onChange={e => setQuestion(e.target.value)}
                    onKeyDown={e => handleKeyDown(e, () => handleChat())}
                    placeholder="Ask about this codebase..."
                    style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', fontSize: 15, color: '#1b1b21', fontFamily: 'Hanken Grotesk, sans-serif' }}
                  />
                  <button
                    onClick={() => handleChat()}
                    disabled={isAsking || !question.trim()}
                    style={{
                      width: 40, height: 40, borderRadius: '50%', border: 'none', cursor: 'pointer',
                      background: question.trim() && !isAsking ? 'linear-gradient(135deg, #006399, #0080c0)' : '#e4e1e9',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      boxShadow: question.trim() ? '0 4px 12px rgba(0,99,153,0.3)' : 'none',
                      transition: 'all 0.2s'
                    }}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={question.trim() && !isAsking ? 'white' : '#bfc7d2'} strokeWidth="2.5">
                      <path d="M5 12h14M12 5l7 7-7 7"/>
                    </svg>
                  </button>
                </div>
                <p style={{ textAlign: 'center', fontSize: 12, color: '#bfc7d2', marginTop: 6 }}>
                  Answers are grounded in the actual source code. Verify output independently.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}