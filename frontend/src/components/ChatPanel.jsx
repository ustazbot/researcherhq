// frontend/src/components/ChatPanel.jsx
import { useState, useRef, useEffect } from 'react'
import { IconArrowUp } from '@tabler/icons-react'
import ReactMarkdown from 'react-markdown'
import { CitationCard } from './CitationCard'
import { parseCitation } from '../utils/parseCitation'

const SOURCE_BADGE = {
  rag_document:  { label: '📄 Your documents',                            bg: 'var(--success-soft)', color: 'var(--success)' },
  web_search:    { label: '🌐 Web sources',                               bg: 'var(--info-soft)', color: 'var(--info)' },
  llm_knowledge: { label: '⚠ General knowledge — verify independently',  bg: 'var(--warning-soft)', color: 'var(--warning)' },
}

const CITE_STYLES = `
.cite-chip {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px;
  background: var(--info-soft); color: var(--info);
  border: 1px solid var(--info);
  border-radius: 50%; font-size: 9px; font-weight: 700;
  cursor: pointer; vertical-align: super; margin: 0 1px;
  position: relative; text-decoration: none;
  font-family: var(--font-mono);
}
.cite-chip:hover .cite-tooltip {
  display: block;
}
.cite-tooltip {
  display: none;
  position: absolute; bottom: 120%; left: 50%; transform: translateX(-50%);
  background: var(--ink); color: var(--bg);
  padding: 4px 8px; border-radius: 4px;
  white-space: nowrap; font-size: 11px; font-weight: 400;
  z-index: 10; pointer-events: none;
  font-family: var(--font-mono);
}
.cite-footnotes {
  margin-top: 12px; padding-top: 10px;
  border-top: 1px solid var(--line);
  font-family: var(--font-mono); font-size: 11px;
  color: var(--ink-soft);
}
`

const MD_STYLES = `
.rhq-md { font-family: var(--font-body); }
.rhq-md h1, .rhq-md h2, .rhq-md h3 { font-family: var(--font-heading); margin: 0.4em 0 0.2em; }
.rhq-md p { margin: 0 0 0.5em; }
.rhq-md p:last-child { margin-bottom: 0; }
.rhq-md ul, .rhq-md ol { padding-left: 1.4em; margin: 0 0 0.5em; }
.rhq-md li { margin: 0.1em 0; }
`

const PILL_STYLES = `
.mode-pill-wrap { position: relative; display: inline-block; margin-bottom: 8px; }
.mode-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px; background: var(--card);
  border: 1px solid var(--line); border-radius: 20px;
  font-family: var(--font-mono); font-size: 11px;
  cursor: pointer; color: var(--ink); user-select: none;
}
.mode-pill:hover { border-color: var(--ink-soft); }
.mode-pill-dropdown {
  position: absolute; bottom: 110%; left: 0;
  background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius-sm); box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  min-width: 200px; z-index: 20; overflow: hidden;
}
.mode-pill-option {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 14px; cursor: pointer;
  font-family: var(--font-mono); font-size: 11px; color: var(--ink);
  background: none; border: none; width: 100%; text-align: left;
}
.mode-pill-option:hover { background: var(--bg); }
.mode-pill-option.active { background: var(--accent-soft); font-weight: 700; }
.mode-credit-hint {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--ink-soft); margin-left: 6px;
}
`

function CiteChip({ index, source }) {
  const label = source ? `${source.filename}, p. ${source.page_number}` : `Source ${index}`
  return (
    <span className="cite-chip" title={label}>
      {index}
      <span className="cite-tooltip">{label}</span>
    </span>
  )
}

const OUTPUT_MODES = [
  { value: 'qa',                label: 'Q&A',               credits: 1,  proOnly: false },
  { value: 'key_findings',      label: 'Key Findings',      credits: 3,  proOnly: false },
  { value: 'executive_summary', label: 'Executive Summary', credits: 5,  proOnly: true  },
  { value: 'literature_review', label: 'Literature Review', credits: 10, proOnly: true  },
  { value: 'research_gap',      label: 'Research Gap',      credits: 10, proOnly: true  },
  { value: 'discovery',         label: 'Topic Discovery',   credits: 1,  proOnly: false },
]

function _relativeTime(isoString) {
  if (!isoString) return ''
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  if (hours < 24) return `${hours} hr ago`
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`
  return new Date(isoString).toLocaleDateString('en-GB')
}

export function ChatPanel({
  messages, loading, query, onQueryChange, onSubmit,
  outputMode, onOutputModeChange, credits, onSendToEditor,
  hasActiveChapter, bottomRef, tier, isDiscoveryMode,
  useWebSearch, onWebSearchToggle, isPro,
  sessions, activeSessionId, onNewSession, onSelectSession, onRenameSession, onDeleteSession,
}) {
  const [pillOpen, setPillOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [renamingId, setRenamingId] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [sessionMenuId, setSessionMenuId] = useState(null)
  const pillRef = useRef(null)
  useEffect(() => {
    function close(e) { if (pillRef.current && !pillRef.current.contains(e.target)) setPillOpen(false) }
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [])

  // Reset to qa if current mode is Pro-only but user is free
  useEffect(() => {
    const current = OUTPUT_MODES.find(m => m.value === outputMode)
    if (current?.proOnly && tier !== 'pro') onOutputModeChange('qa')
  }, [tier])

  function renderContent(text, sources) {
    const segments = parseCitation(text, sources || [])
    // Check if any cite segments exist
    const hasCites = segments.some(s => s.type === 'cite')
    // Collect unique cited sources for footnote
    const cited = []
    const seen = new Set()
    segments.forEach(s => {
      if (s.type === 'cite' && !seen.has(s.index)) {
        seen.add(s.index)
        cited.push(s)
      }
    })
    return (
      <>
        <div>
          {segments.map((seg, i) =>
            seg.type === 'text'
              ? <div key={i} className="rhq-md"><ReactMarkdown>{seg.content}</ReactMarkdown></div>
              : <CiteChip key={i} index={seg.index} source={seg.source} />
          )}
        </div>
        {hasCites && cited.length > 0 && (
          <div className="cite-footnotes">
            {cited.map(s => (
              <div key={s.index}>
                [{s.index}] {s.source ? `${s.source.filename}, p. ${s.source.page_number}` : `Source ${s.index}`}
              </div>
            ))}
          </div>
        )}
      </>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', height: '100%', position: 'relative' }}>
      <style>{CITE_STYLES}</style>
      <style>{MD_STYLES}</style>

      {/* Chat Header with session switcher */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderBottom: '1px solid var(--line)', background: 'var(--card)', flexShrink: 0 }}>
        <button
          onClick={() => setDrawerOpen(v => !v)}
          title="Chat Sessions"
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'none', border: '1px solid var(--line)',
            borderRadius: 6, padding: '4px 8px', cursor: 'pointer',
            color: 'var(--ink)', fontSize: 13, maxWidth: 200, flex: 1,
          }}
        >
          <span>≡</span>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, textAlign: 'left' }}>
            {sessions?.find(s => s.id === activeSessionId)?.title || 'New Chat'}
          </span>
          <span style={{ color: 'var(--ink-soft)', fontSize: 10 }}>▼</span>
        </button>
        {isDiscoveryMode && (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 10,
            background: tier === 'pro' ? 'var(--accent)' : 'var(--accent-soft)',
            color: 'var(--ink)', padding: '2px 8px', borderRadius: 4, flexShrink: 0,
          }}>
            {tier === 'pro' ? 'Full Discovery' : 'Discovery (Free)'}
          </span>
        )}
      </div>

      {/* Session Drawer */}
      {drawerOpen && (
        <>
          <div
            onClick={() => setDrawerOpen(false)}
            style={{ position: 'absolute', inset: 0, zIndex: 10, background: 'rgba(0,0,0,0.15)' }}
          />
          <div style={{
            position: 'absolute', top: 0, left: 0, bottom: 0,
            width: 240, zIndex: 11,
            background: 'var(--card)',
            borderRight: '1px solid var(--line)',
            display: 'flex', flexDirection: 'column',
            boxShadow: '2px 0 8px rgba(0,0,0,0.08)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', borderBottom: '1px solid var(--line)' }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>Chat Sessions</span>
              <button onClick={() => setDrawerOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 18 }}>×</button>
            </div>
            <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--line)' }}>
              <button
                onClick={() => { onNewSession?.(); setDrawerOpen(false); }}
                style={{
                  width: '100%', padding: '7px 12px',
                  background: 'var(--accent)', color: 'white',
                  border: 'none', borderRadius: 6, cursor: 'pointer',
                  fontSize: 13, fontWeight: 500,
                  display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center'
                }}
              >
                + New Chat
              </button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '6px 0' }}>
              {(sessions || []).map(sess => (
                <div key={sess.id} style={{ position: 'relative', background: sess.id === activeSessionId ? 'var(--accent-soft)' : 'transparent' }}>
                  {renamingId === sess.id ? (
                    <div style={{ padding: '6px 12px', display: 'flex', gap: 6 }}>
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={e => setRenameValue(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') { onRenameSession?.(sess.id, renameValue); setRenamingId(null); }
                          if (e.key === 'Escape') setRenamingId(null)
                        }}
                        style={{ flex: 1, fontSize: 13, padding: '3px 6px', border: '1px solid var(--accent)', borderRadius: 4, background: 'var(--card)', color: 'var(--ink)' }}
                      />
                      <button
                        onClick={() => { onRenameSession?.(sess.id, renameValue); setRenamingId(null); }}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)' }}
                      >✓</button>
                    </div>
                  ) : (
                    <div
                      style={{ display: 'flex', alignItems: 'center', padding: '8px 12px', cursor: 'pointer' }}
                      onClick={() => { onSelectSession?.(sess.id); setDrawerOpen(false); }}
                    >
                      <span style={{ width: 6, height: 6, borderRadius: '50%', flexShrink: 0, marginRight: 8, background: sess.id === activeSessionId ? 'var(--accent)' : 'transparent' }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sess.title}</div>
                        <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginTop: 1 }}>{_relativeTime(sess.updated_at)}</div>
                      </div>
                      <button
                        onClick={e => { e.stopPropagation(); setSessionMenuId(sessionMenuId === sess.id ? null : sess.id); }}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', padding: '2px 4px', fontSize: 16 }}
                      >⋯</button>
                    </div>
                  )}
                  {sessionMenuId === sess.id && (
                    <div style={{
                      position: 'absolute', right: 8, top: '100%', zIndex: 20,
                      background: 'var(--card)', border: '1px solid var(--line)',
                      borderRadius: 6, boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                      minWidth: 120, overflow: 'hidden'
                    }}>
                      <button
                        onClick={e => { e.stopPropagation(); setRenamingId(sess.id); setRenameValue(sess.title); setSessionMenuId(null); }}
                        style={{ width: '100%', padding: '8px 12px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', fontSize: 13, color: 'var(--ink)' }}
                      >✏️ Rename</button>
                      <button
                        onClick={e => {
                          e.stopPropagation()
                          if (window.confirm('Delete this session? Messages cannot be recovered.')) onDeleteSession?.(sess.id)
                          setSessionMenuId(null)
                        }}
                        style={{ width: '100%', padding: '8px 12px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', fontSize: 13, color: 'var(--danger)' }}
                      >🗑️ Delete</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div style={{ flex: 1, overflow: 'auto', padding: '20px 16px' }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--ink-soft)' }}>
            <p style={{ fontSize: 15, fontWeight: 500 }}>Upload a document to start asking questions.</p>
            <p style={{ fontSize: 13 }}>All answers are grounded in your documents.</p>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} style={{
            marginBottom: 20, display: 'flex', flexDirection: 'column',
            alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{
              maxWidth: '90%',
              background: msg.role === 'user' ? 'var(--ink)' : msg.role === 'error' ? 'var(--danger-soft)' : 'var(--card)',
              color: msg.role === 'user' ? 'var(--bg)' : msg.role === 'error' ? 'var(--danger)' : 'var(--ink)',
              border: msg.role === 'user' ? 'none' : `1px solid ${msg.role === 'error' ? 'var(--danger)' : 'var(--line)'}`,
              borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
              padding: '12px 16px', fontFamily: 'var(--font-body)', fontSize: 14,
              lineHeight: 1.6, whiteSpace: msg.role === 'assistant' ? undefined : 'pre-wrap',
            }}>
              {msg.role === 'assistant' && msg.source_type && SOURCE_BADGE[msg.source_type] && (
                <div style={{
                  display: 'inline-block',
                  padding: '2px 8px',
                  borderRadius: 4,
                  fontSize: 11,
                  fontFamily: 'var(--font-mono)',
                  marginBottom: 8,
                  background: SOURCE_BADGE[msg.source_type].bg,
                  color: SOURCE_BADGE[msg.source_type].color,
                }}>
                  {SOURCE_BADGE[msg.source_type].label}
                </div>
              )}
              {msg.role === 'assistant' ? renderContent(msg.content, msg.sources) : msg.content}
              {msg.kredit_used && (
                <span style={{ display: 'block', marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: 10, opacity: 0.6 }}>
                  {msg.kredit_used} credits
                </span>
              )}
            </div>

            {/* Butang Hantar ke Editor — hanya untuk AI answers */}
            {msg.role === 'assistant' && (
              <button
                onClick={() => onSendToEditor(msg.content)}
                disabled={!hasActiveChapter}
                title={!hasActiveChapter ? 'Select a chapter first to send to the Editor' : 'Send this answer to the active chapter as a suggestion'}
                style={{
                  marginTop: 4, padding: '3px 10px',
                  background: 'transparent',
                  border: '1px solid var(--line)',
                  borderRadius: 4, cursor: hasActiveChapter ? 'pointer' : 'not-allowed',
                  fontFamily: 'var(--font-mono)', fontSize: 11,
                  color: hasActiveChapter ? 'var(--ink)' : 'var(--ink-soft)',
                  opacity: hasActiveChapter ? 1 : 0.5,
                }}
              >
                → Send to Editor
              </button>
            )}

            {msg.sources && msg.sources.length > 0 && (
              <div style={{ marginTop: 8, maxWidth: '90%', width: '100%' }}>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)', margin: '0 0 4px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Sources ({msg.sources.length})
                </p>
                {msg.sources.map(s => <CitationCard key={s.chunk_id} source={s} />)}
              </div>
            )}
            {msg.web_citations?.length > 0 && (
              <div style={{ marginTop: 8, maxWidth: '90%', width: '100%', borderTop: '1px solid var(--line)', paddingTop: 8 }}>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)', margin: '0 0 4px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Sources:
                </p>
                {msg.web_citations.map((c, i) => (
                  <a
                    key={i}
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'block', fontSize: 12,
                      color: 'var(--accent)', marginBottom: 2,
                      wordBreak: 'break-all',
                    }}
                  >
                    [{i + 1}] {c.title || c.url}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', marginBottom: 20 }}>
            <div style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: '4px 16px 16px 16px', padding: '12px 16px' }}>
              <span style={{ color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>Thinking...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div id="rhq-tour-chat-input" style={{ borderTop: '1px solid var(--line)', padding: '12px 16px', background: 'var(--card)', flexShrink: 0 }}>
        {/* Mode pill */}
        <div className="mode-pill-wrap" ref={pillRef}>
          <style>{PILL_STYLES}</style>
          <button
            className="mode-pill"
            onClick={() => setPillOpen(o => !o)}
            type="button"
          >
            {OUTPUT_MODES.find(m => m.value === outputMode)?.label ?? 'Q&A'}
            <span>▾</span>
          </button>
          {pillOpen && (
            <div className="mode-pill-dropdown">
              {OUTPUT_MODES
                .filter(m => m.value !== 'discovery' || isDiscoveryMode)
                .map(m => {
                  const locked = m.proOnly && tier !== 'pro'
                  return (
                    <button
                      key={m.value}
                      className={`mode-pill-option${outputMode === m.value ? ' active' : ''}${locked ? ' locked' : ''}`}
                      onClick={locked ? undefined : () => { onOutputModeChange(m.value); setPillOpen(false) }}
                      disabled={locked}
                      style={locked ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
                    >
                      {m.label}
                      {locked
                        ? <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, background: 'var(--accent)', color: 'var(--ink)', borderRadius: 3, padding: '1px 5px', marginLeft: 4 }}>PRO</span>
                        : <span className="mode-credit-hint">{m.credits} credits</span>
                      }
                    </button>
                  )
                })}
            </div>
          )}
        </div>
        <span className="mode-credit-hint" style={{ display: 'inline-block', marginBottom: 8 }}>
          ≈ {OUTPUT_MODES.find(m => m.value === outputMode)?.credits ?? 1} credits
        </span>
        {/* Web Search Toggle */}
        <div style={{ marginBottom: 8 }}>
          <button
            type="button"
            onClick={() => isPro && onWebSearchToggle && onWebSearchToggle(v => !v)}
            title={isPro ? (useWebSearch ? 'Mode: Web Search' : 'Mode: Document') : 'Web search — Pro only'}
            style={{
              padding: '4px 10px', borderRadius: 6, border: '1px solid',
              borderColor: useWebSearch ? 'var(--info)' : 'var(--line)',
              background: useWebSearch ? 'var(--info-soft)' : 'transparent',
              color: useWebSearch ? 'var(--info)' : 'var(--ink-soft)',
              cursor: isPro ? 'pointer' : 'not-allowed',
              opacity: isPro ? 1 : 0.5,
              fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4,
            }}
          >
            {useWebSearch ? '🔍 Web' : '📄 Document'}
          </button>
          {!isPro && (
            <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--ink-soft)' }}>Web — Pro only</span>
          )}
        </div>
        <form onSubmit={onSubmit} style={{ display: 'flex', gap: 6 }}>
          <input
            value={query} onChange={e => onQueryChange(e.target.value)}
            placeholder="Ask a question..."
            disabled={loading}
            style={{
              flex: 1, padding: '10px 14px',
              border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
              fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', outline: 'none',
            }}
          />
          <button type="submit" disabled={loading || !query.trim()} style={{
            width: 42, height: 42, flexShrink: 0,
            background: loading || !query.trim() ? 'var(--line)' : 'var(--accent)',
            border: 'none', borderRadius: 'var(--radius-sm)',
            cursor: loading || !query.trim() ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'background 0.1s',
          }}>
            <IconArrowUp size={20} stroke={2.5} color="var(--ink)" />
          </button>
        </form>
      </div>
    </div>
  )
}
