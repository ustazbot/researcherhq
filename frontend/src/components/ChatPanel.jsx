// frontend/src/components/ChatPanel.jsx
import { CitationCard } from './CitationCard'

const OUTPUT_MODES = [
  { value: 'qa', label: 'Soal-Jawab', credits: 1 },
  { value: 'key_findings', label: 'Dapatan Utama', credits: 3 },
  { value: 'executive_summary', label: 'Ringkasan Eksekutif', credits: 5 },
  { value: 'literature_review', label: 'Sorotan Kajian', credits: 10 },
  { value: 'discovery', label: 'Mod Penemuan Topik', credits: 1 },
]

export function ChatPanel({ messages, loading, query, onQueryChange, onSubmit, outputMode, onOutputModeChange, credits, onSendToEditor, hasActiveChapter, bottomRef, tier, isDiscoveryMode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', height: '100%' }}>
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
              lineHeight: 1.6, whiteSpace: 'pre-wrap',
            }}>
              {msg.content}
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
        <div style={{ display: 'flex', gap: 4, marginBottom: 10, flexWrap: 'wrap' }}>
          {OUTPUT_MODES.map(m => (
            <button key={m.value} onClick={() => onOutputModeChange(m.value)} style={{
              padding: '3px 8px',
              background: outputMode === m.value ? 'var(--ink)' : 'transparent',
              color: outputMode === m.value ? 'var(--bg)' : 'var(--ink-soft)',
              border: `1px solid ${outputMode === m.value ? 'var(--ink)' : 'var(--line)'}`,
              borderRadius: 5, fontFamily: 'var(--font-mono)', fontSize: 10, cursor: 'pointer',
            }}>
              {m.label} ({m.credits}kr)
            </button>
          ))}
        </div>
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
