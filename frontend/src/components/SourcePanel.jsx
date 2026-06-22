import { useState } from 'react'
import api from '../api/client'

const CATEGORIES = [
  { value: 'artikel', label: 'Artikel Rujukan', icon: '📄' },
  { value: 'catatan_sv', label: 'Catatan SV', icon: '📝' },
  { value: 'draf', label: 'Draf Sendiri', icon: '📑' },
  { value: 'data', label: 'Data / Transkrip', icon: '📊' },
]

export function SourcePanel({ documents, onUpload, tier, uploading, collapsed, onToggleCollapse, onDeleteDoc }) {
  const [activeCategory, setActiveCategory] = useState('artikel')
  const [previewDocId, setPreviewDocId] = useState(null)
  const [previewText, setPreviewText] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState(false)

  async function handlePreviewDoc(docId) {
    if (previewDocId === docId) {
      setPreviewDocId(null); setPreviewText(null); return
    }
    setPreviewDocId(docId); setPreviewLoading(true); setPreviewError(false)
    try {
      const { data } = await api.get(`/documents/${docId}/preview`)
      setPreviewText(data)
    } catch {
      setPreviewError(true)
    } finally {
      setPreviewLoading(false)
    }
  }

  const uploadDisabled = tier !== 'pro' && (documents || []).length >= 1

  const grouped = CATEGORIES.map(cat => ({
    ...cat,
    docs: (documents || []).filter(d => d.category === cat.value)
  }))

  function handleDelete(e, docId, filename) {
    e.stopPropagation()
    if (window.confirm(`Padam "${filename}"? Semua chunk dan embedding dokumen ini akan dibuang.`)) {
      onDeleteDoc(docId)
    }
  }

  if (collapsed) {
    return (
      <div style={{
        width: 36, flexShrink: 0, borderRight: '1px solid var(--line)',
        background: 'var(--card)', display: 'flex', flexDirection: 'column', alignItems: 'center',
        paddingTop: 12,
      }}>
        <button
          onClick={onToggleCollapse}
          title="Buka panel Sumber"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--ink-soft)', fontSize: 16, padding: 4,
          }}
        >›</button>
      </div>
    )
  }

  return (
    <div style={{
      width: 260, flexShrink: 0, borderRight: '1px solid var(--line)',
      display: 'flex', flexDirection: 'column', background: 'var(--card)',
      overflow: 'hidden',
    }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
          Sumber
        </span>
        <button
          onClick={onToggleCollapse}
          title="Tutup panel Sumber"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 16, padding: 0 }}
        >‹</button>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {grouped.map(cat => (
          <div key={cat.value}>
            <button
              onClick={() => setActiveCategory(activeCategory === cat.value ? null : cat.value)}
              style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                width: '100%', padding: '8px 16px', background: 'transparent', border: 'none',
                fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)',
                cursor: 'pointer', textAlign: 'left',
              }}
            >
              <span>{cat.icon} {cat.label}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)' }}>
                {cat.docs.length}
              </span>
            </button>
            {activeCategory === cat.value && cat.docs.map(doc => (
              <div key={doc.id} style={{ padding: '6px 16px 6px 32px' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 4 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p
                      onClick={() => handlePreviewDoc(doc.id)}
                      style={{
                        margin: 0, fontFamily: 'var(--font-body)', fontSize: 12,
                        color: previewDocId === doc.id ? 'var(--accent)' : 'var(--ink-soft)',
                        wordBreak: 'break-word', cursor: 'pointer', textDecoration: previewDocId === doc.id ? 'underline' : 'none',
                      }}
                    >
                      {doc.filename}
                    </p>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)' }}>
                      {doc.chunk_count} chunk
                    </span>
                  </div>
                  <button
                    onClick={e => handleDelete(e, doc.id, doc.filename)}
                    title="Padam dokumen ini"
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 14, padding: '2px 4px', flexShrink: 0, lineHeight: 1 }}
                  >×</button>
                </div>

                {/* Preview block */}
                {previewDocId === doc.id && (
                  <div style={{
                    marginTop: 6, background: 'var(--bg)', border: '1px solid var(--line)',
                    borderRadius: 'var(--radius-sm)', padding: '10px 12px',
                    fontSize: 12, maxHeight: 200, overflowY: 'auto', whiteSpace: 'pre-wrap',
                    fontFamily: 'var(--font-body)', color: 'var(--ink-soft)',
                  }}>
                    {previewLoading && 'Memuatkan pratonton...'}
                    {previewError && 'Gagal memuatkan — cuba lagi.'}
                    {!previewLoading && !previewError && previewText && (
                      <>
                        <p style={{ margin: '0 0 6px', whiteSpace: 'pre-wrap' }}>{previewText.preview_text}</p>
                        <p style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)' }}>
                          Menunjukkan {previewText.showing_chunks} daripada {previewText.chunk_count} bahagian
                        </p>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>

      <div style={{ padding: 12, borderTop: '1px solid var(--line)' }}>
        <button
          onClick={uploadDisabled || uploading ? undefined : onUpload}
          disabled={uploadDisabled || uploading}
          title={uploadDisabled ? 'Free tier: 1 PDF sahaja. Naik taraf ke Pro untuk sehingga 5 PDF.' : ''}
          style={{
            width: '100%', padding: '8px 0',
            background: uploadDisabled ? 'var(--line)' : 'var(--accent-soft)',
            border: `1px solid ${uploadDisabled ? 'var(--line)' : 'var(--accent)'}`,
            borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 13,
            cursor: uploadDisabled || uploading ? 'not-allowed' : 'pointer',
            color: uploadDisabled ? 'var(--ink-soft)' : 'var(--ink)',
            opacity: uploadDisabled || uploading ? 0.6 : 1,
          }}
        >
          {uploadDisabled ? '🔒 Had Dicapai' : uploading ? 'Memproses...' : '+ Muat naik'}
        </button>
      </div>
    </div>
  )
}
