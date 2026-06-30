import { useState } from 'react'

export function CitationCard({ source }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={{
      border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
      overflow: 'hidden', marginBottom: 8,
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '8px 12px', background: 'var(--bg)',
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-soft)' }}>
          📄 {source.filename}, p. {source.page_number}
        </span>
        <button
          onClick={() => setExpanded(!expanded)}
          style={{
            padding: '4px 10px', background: 'transparent',
            border: '1px solid var(--line)', borderRadius: 4,
            fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer',
            color: 'var(--ink)',
          }}
        >
          {expanded ? '▲ Close' : '▼ View Source'}
        </button>
      </div>
      {expanded && (
        <div style={{
          padding: '12px 14px', background: 'var(--card)',
          borderTop: '1px solid var(--line)',
          fontFamily: 'var(--font-body)', fontSize: 13,
          color: 'var(--ink-soft)', lineHeight: 1.6,
        }}>
          {source.text_preview}
        </div>
      )}
    </div>
  )
}
