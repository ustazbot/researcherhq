// frontend/src/components/ChapterEditor.jsx
import { useState, useEffect } from 'react'

const TOOLTIP_KEY = 'rhq_suggestion_tooltip_seen'

export function ChapterEditor({ chapter, content, pendingSuggestion, onAccept, onReject, onSave, saving }) {
  const [editText, setEditText] = useState(content || '')
  const [showTooltip, setShowTooltip] = useState(false)

  // Sync edit text bila chapter bertukar atau content load dari API
  useEffect(() => {
    if (!pendingSuggestion) setEditText(content || '')
  }, [content, chapter?.id])

  // First-time tooltip bila ada cadangan AI buat pertama kali
  useEffect(() => {
    if (pendingSuggestion && !localStorage.getItem(TOOLTIP_KEY)) {
      setShowTooltip(true)
    }
  }, [pendingSuggestion])

  function dismissTooltip() {
    localStorage.setItem(TOOLTIP_KEY, '1')
    setShowTooltip(false)
  }

  if (!chapter) {
    return (
      <div style={{
        flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--bg)', color: 'var(--ink-soft)',
        fontFamily: 'var(--font-body)', fontSize: 15, padding: 40, textAlign: 'center',
      }}>
        <div>
          <p style={{ marginBottom: 8, fontWeight: 500 }}>Pilih bab dari panel Struktur Tesis.</p>
          <p style={{ fontSize: 13 }}>Atau tambah bab baru untuk mula menulis.</p>
        </div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg)' }}>
      {/* Header */}
      <div style={{
        padding: '12px 24px', borderBottom: '1px solid var(--line)',
        background: 'var(--card)', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', flexShrink: 0,
      }}>
        <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16, color: 'var(--ink)' }}>
          {chapter.title}
        </span>
        {!pendingSuggestion && (
          <button
            onClick={() => onSave(editText)}
            disabled={saving || editText === (content || '')}
            style={{
              padding: '6px 16px', background: 'var(--accent)', border: 'none',
              borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)',
              fontWeight: 700, fontSize: 13, cursor: saving ? 'wait' : 'pointer',
              opacity: (saving || editText === (content || '')) ? 0.5 : 1,
            }}
          >
            {saving ? 'Menyimpan...' : 'Simpan'}
          </button>
        )}
      </div>

      {/* First-time tooltip */}
      {showTooltip && (
        <div style={{
          margin: '12px 24px 0', padding: '12px 16px',
          background: 'var(--accent-soft)', border: '1px solid var(--accent)',
          borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'flex-start',
          gap: 12,
        }}>
          <span style={{ fontSize: 18 }}>💡</span>
          <div style={{ flex: 1 }}>
            <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)' }}>
              Ni cadangan AI — klik <strong>Terima</strong> untuk masuk ke bab, atau <strong>Tolak</strong> untuk buang.
              Sama macam Track Changes dalam Word yang penyelia guna untuk bagi maklum balas.
            </p>
          </div>
          <button onClick={dismissTooltip} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--ink-soft)', fontSize: 16, flexShrink: 0, padding: 0,
          }}>×</button>
        </div>
      )}

      {/* Suggestion mode */}
      {pendingSuggestion ? (
        <div style={{ flex: 1, overflow: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Suggestion banner */}
          <div style={{
            borderLeft: '4px solid var(--accent)', paddingLeft: 16,
            background: 'var(--accent-soft)', borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
            padding: '16px 16px 16px 20px',
          }}>
            <p style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase',
              letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 8px',
            }}>
              Cadangan AI
            </p>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 15, lineHeight: 1.7, color: 'var(--ink)', margin: 0, whiteSpace: 'pre-wrap' }}>
              {pendingSuggestion.text}
            </p>
          </div>

          {/* Terima / Tolak */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => onAccept(pendingSuggestion.text)}
              disabled={saving}
              style={{
                padding: '10px 24px', background: 'var(--accent)', border: 'none',
                borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)',
                fontWeight: 700, fontSize: 14, cursor: saving ? 'wait' : 'pointer',
                opacity: saving ? 0.6 : 1,
              }}
            >
              {saving ? 'Menyimpan...' : 'Terima'}
            </button>
            <button
              onClick={onReject}
              disabled={saving}
              style={{
                padding: '10px 24px', background: 'transparent',
                border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
                fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14,
                cursor: 'pointer', color: 'var(--ink-soft)',
              }}
            >
              Tolak
            </button>
          </div>

          {/* Current content (read-only, muted) — only show if not empty */}
          {(content || '').trim() && (
            <div>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)', margin: '0 0 8px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Kandungan semasa (tidak berubah jika Tolak)
              </p>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 14, lineHeight: 1.7, color: 'var(--ink-soft)', whiteSpace: 'pre-wrap' }}>
                {content}
              </p>
            </div>
          )}
        </div>
      ) : (
        /* Edit mode */
        <textarea
          value={editText}
          onChange={e => setEditText(e.target.value)}
          placeholder="Mula taip kandungan bab di sini..."
          style={{
            flex: 1, padding: '24px', border: 'none', outline: 'none', resize: 'none',
            fontFamily: 'var(--font-body)', fontSize: 15, lineHeight: 1.8,
            background: 'var(--bg)', color: 'var(--ink)',
          }}
        />
      )}
    </div>
  )
}
