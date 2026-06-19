const STATUS_LABEL = { draft: 'Draf', dalam_proses: 'Dalam Proses', siap: 'Siap' }
const STATUS_COLOR = { draft: 'var(--line)', dalam_proses: 'var(--accent-soft)', siap: '#D1FAE5' }

export function ThesisPanel({ chapters, onExport, tier, projectId }) {
  const done = (chapters || []).filter(c => c.status === 'siap').length
  const total = (chapters || []).length

  return (
    <div style={{
      width: 260, flexShrink: 0, borderLeft: '1px solid var(--line)',
      display: 'flex', flexDirection: 'column', background: 'var(--card)',
      position: 'relative',
    }}>
      {tier !== 'pro' && (
        <div style={{
          position: 'absolute', inset: 0,
          background: 'rgba(248,246,241,0.88)',
          backdropFilter: 'blur(2px)',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          zIndex: 10, padding: 24, textAlign: 'center',
        }}>
          <span style={{ fontSize: 32, marginBottom: 12 }}>🔒</span>
          <p style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16, margin: '0 0 8px' }}>
            Thesis Workspace
          </p>
          <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)', margin: '0 0 16px' }}>
            Urus bab, assign output AI, dan export .docx — hanya untuk Pro.
          </p>
          <button
            onClick={() => window.location.href = '/upgrade'}
            style={{
              padding: '10px 20px', background: 'var(--accent)', border: 'none',
              borderRadius: 'var(--radius-sm)', fontWeight: 700, cursor: 'pointer',
              fontFamily: 'var(--font-heading)', fontSize: 14,
            }}
          >
            Naik taraf ke Pro — RM39/bulan
          </button>
        </div>
      )}

      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)' }}>
          Struktur Tesis
        </span>
        {total > 0 && (
          <span style={{ float: 'right', fontFamily: 'var(--font-mono)', fontSize: 11, color: done === total ? '#16A34A' : 'var(--ink-soft)' }}>
            {done}/{total} siap
          </span>
        )}
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {total === 0 ? (
          <p style={{ padding: '16px', color: 'var(--ink-soft)', fontSize: 13 }}>
            Tiada bab lagi. Tambah bab pertama anda.
          </p>
        ) : (
          (chapters || []).map(chap => (
            <div key={chap.id} style={{
              padding: '8px 16px',
              borderBottom: '1px solid var(--line)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink)', flex: 1 }}>
                  {chap.title}
                </span>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, padding: '2px 6px', borderRadius: 4,
                  background: STATUS_COLOR[chap.status] || 'var(--line)', color: 'var(--ink)',
                  flexShrink: 0,
                }}>
                  {STATUS_LABEL[chap.status] || chap.status}
                </span>
              </div>
              {tier === 'pro' ? (
                <button onClick={() => onExport(chap.id)} style={{
                  marginTop: 6, padding: '3px 8px', fontSize: 11,
                  background: 'transparent', border: '1px solid var(--line)',
                  borderRadius: 4, cursor: 'pointer', fontFamily: 'var(--font-mono)',
                }}>
                  Export .docx
                </button>
              ) : (
                <button disabled style={{
                  marginTop: 6, padding: '3px 8px', fontSize: 11,
                  background: 'var(--line)', border: 'none',
                  borderRadius: 4, cursor: 'not-allowed', fontFamily: 'var(--font-mono)',
                  color: 'var(--ink-soft)',
                }}>
                  🔒 Pro
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
