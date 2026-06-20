import { useState } from 'react'

const CATEGORIES = [
  { value: 'artikel', label: 'Artikel Rujukan', icon: '📄' },
  { value: 'catatan_sv', label: 'Catatan SV', icon: '📝' },
  { value: 'draf', label: 'Draf Sendiri', icon: '📑' },
  { value: 'data', label: 'Data / Transkrip', icon: '📊' },
]

export function SourcePanel({ documents, onUpload, tier, uploading, collapsed, onToggleCollapse, onDeleteDoc }) {
  const [activeCategory, setActiveCategory] = useState('artikel')
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
              <div key={doc.id} style={{
                padding: '6px 16px 6px 32px',
                display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 4,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-soft)', wordBreak: 'break-word' }}>
                    {doc.filename}
                  </p>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-soft)' }}>
                    {doc.chunk_count} chunk
                  </span>
                </div>
                <button
                  onClick={e => handleDelete(e, doc.id, doc.filename)}
                  title="Padam dokumen ini"
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--ink-soft)', fontSize: 14, padding: '2px 4px',
                    flexShrink: 0, lineHeight: 1,
                  }}
                >×</button>
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
