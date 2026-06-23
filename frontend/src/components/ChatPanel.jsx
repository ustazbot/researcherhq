// frontend/src/components/ChatPanel.jsx
import { useState, useRef, useEffect } from 'react'
import { CitationCard } from './CitationCard'
import { parseCitation } from '../utils/parseCitation'

const CITE_STYLES = `
.cite-chip {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px;
  background: #EEF2FF; color: #4F46E5;
  border: 1px solid #C7D2FE;
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
  const label = source ? `${source.filename}, ms. ${source.page_number}` : `Sumber ${index}`
  return (
    <span className="cite-chip" title={label}>
      {index}
      <span className="cite-tooltip">{label}</span>
    </span>
  )
}

const OUTPUT_MODES = [
  { value: 'qa', label: 'Soal-Jawab', credits: 1 },
  { value: 'key_findings', label: 'Dapatan Utama', credits: 3 },
  { value: 'executive_summary', label: 'Ringkasan Eksekutif', credits: 5 },
  { value: 'literature_review', label: 'Sorotan Kajian', credits: 10 },
  { value: 'discovery', label: 'Mod Penemuan Topik', credits: 1 },
]

export function ChatPanel({ messages, loading, query, onQueryChange, onSubmit, outputMode, onOutputModeChange, credits, onSendToEditor, hasActiveChapter, bottomRef, tier, isDiscoveryMode }) {
  const [pillOpen, setPillOpen] = useState(false)
  const pillRef = useRef(null)
  useEffect(() => {
    function close(e) { if (pillRef.current && !pillRef.current.contains(e.target)) setPillOpen(false) }
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [])

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
        <span style={{ whiteSpace: 'pre-wrap' }}>
          {segments.map((seg, i) =>
            seg.type === 'text'
              ? <span key={i}>{seg.content}</span>
              : <CiteChip key={i} index={seg.index} source={seg.source} />
          )}
        </span>
        {hasCites && cited.length > 0 && (
          <div className="cite-footnotes">
            {cited.map(s => (
              <div key={s.index}>
                [{s.index}] {s.source ? `${s.source.filename}, ms. ${s.source.page_number}` : `Sumber ${s.index}`}
              </div>
            ))}
          </div>
        )}
      </>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
      <style>{CITE_STYLES}</style>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', background: 'var(--card)', flexShrink: 0 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
          Chat AI
        </span>
        {isDiscoveryMode && (
          <div style={{ marginTop: 4 }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 10,
              background: tier === 'pro' ? 'var(--accent)' : 'var(--accent-soft)',
              color: 'var(--ink)', padding: '2px 8px', borderRadius: 4,
            }}>
              {tier === 'pro' ? 'Discovery Penuh' : 'Discovery Ringkas (Free)'}
            </span>
          </div>
        )}
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '20px 16px' }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--ink-soft)' }}>
            <p style={{ fontSize: 15, fontWeight: 500 }}>Muat naik dokumen dan mula bertanya.</p>
            <p style={{ fontSize: 13 }}>Semua jawapan bersumberkan dokumen anda sahaja.</p>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} style={{
            marginBottom: 20, display: 'flex', flexDirection: 'column',
            alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{
              maxWidth: '90%',
              background: msg.role === 'user' ? 'var(--ink)' : msg.role === 'error' ? '#FEF2F2' : 'var(--card)',
              color: msg.role === 'user' ? 'var(--bg)' : msg.role === 'error' ? '#EF4444' : 'var(--ink)',
              border: msg.role === 'user' ? 'none' : `1px solid ${msg.role === 'error' ? '#FECACA' : 'var(--line)'}`,
              borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
              padding: '12px 16px', fontFamily: 'var(--font-body)', fontSize: 14,
              lineHeight: 1.6, whiteSpace: msg.role === 'assistant' ? undefined : 'pre-wrap',
            }}>
              {msg.role === 'assistant' ? renderContent(msg.content, msg.sources) : msg.content}
              {msg.kredit_used && (
                <span style={{ display: 'block', marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: 10, opacity: 0.6 }}>
                  {msg.kredit_used} kredit
                </span>
              )}
            </div>

            {/* Butang Hantar ke Editor — hanya untuk AI answers */}
            {msg.role === 'assistant' && (
              <button
                onClick={() => onSendToEditor(msg.content)}
                disabled={!hasActiveChapter}
                title={!hasActiveChapter ? 'Pilih bab dahulu untuk hantar ke Editor' : 'Hantar jawapan ini ke bab aktif sebagai cadangan'}
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
                → Hantar ke Editor
              </button>
            )}

            {msg.sources && msg.sources.length > 0 && (
              <div style={{ marginTop: 8, maxWidth: '90%', width: '100%' }}>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)', margin: '0 0 4px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Sumber ({msg.sources.length})
                </p>
                {msg.sources.map(s => <CitationCard key={s.chunk_id} source={s} />)}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', marginBottom: 20 }}>
            <div style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: '4px 16px 16px 16px', padding: '12px 16px' }}>
              <span style={{ color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>Berfikir...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div style={{ borderTop: '1px solid var(--line)', padding: '12px 16px', background: 'var(--card)', flexShrink: 0 }}>
        {/* Mode pill */}
        <div className="mode-pill-wrap" ref={pillRef}>
          <style>{PILL_STYLES}</style>
          <button
            className="mode-pill"
            onClick={() => setPillOpen(o => !o)}
            type="button"
          >
            {OUTPUT_MODES.find(m => m.value === outputMode)?.label ?? 'Soal-Jawab'}
            <span>▾</span>
          </button>
          {pillOpen && (
            <div className="mode-pill-dropdown">
              {OUTPUT_MODES
                .filter(m => m.value !== 'discovery' || isDiscoveryMode)
                .map(m => (
                  <button
                    key={m.value}
                    className={`mode-pill-option${outputMode === m.value ? ' active' : ''}`}
                    onClick={() => { onOutputModeChange(m.value); setPillOpen(false) }}
                  >
                    {m.label}
                    <span className="mode-credit-hint">{m.credits} kredit</span>
                  </button>
                ))}
            </div>
          )}
        </div>
        <span className="mode-credit-hint" style={{ display: 'inline-block', marginBottom: 8 }}>
          ≈ {OUTPUT_MODES.find(m => m.value === outputMode)?.credits ?? 1} kredit
        </span>
        <form onSubmit={onSubmit} style={{ display: 'flex', gap: 6 }}>
          <input
            value={query} onChange={e => onQueryChange(e.target.value)}
            placeholder="Tanya soalan..."
            disabled={loading}
            style={{
              flex: 1, padding: '10px 14px',
              border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
              fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', outline: 'none',
            }}
          />
          <button type="submit" disabled={loading || !query.trim()} style={{
            padding: '10px 16px', background: 'var(--accent)', color: 'var(--ink)',
            border: 'none', borderRadius: 'var(--radius-sm)',
            fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14, cursor: 'pointer',
          }}>→</button>
        </form>
      </div>
    </div>
  )
}
