export function CreditTank({ remaining, total, resetDate, onTopup }) {
  const pct = Math.max(0, Math.min(100, (remaining / total) * 100))
  const low = pct < 20
  const resetStr = resetDate
    ? new Date(resetDate).toLocaleDateString('ms-MY', { day: 'numeric', month: 'long', year: 'numeric' })
    : '—'

  return (
    <div style={{
      background: 'var(--card)', border: '1px solid var(--line)',
      borderRadius: 'var(--radius-md)', padding: '16px 20px', minWidth: 240,
    }}>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 11,
        letterSpacing: '0.08em', textTransform: 'uppercase',
        color: 'var(--ink-soft)', marginBottom: 10,
      }}>
        Research Credits
      </div>
      <div style={{
        height: 8, background: 'var(--line)', borderRadius: 4,
        marginBottom: 8, overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: low ? '#EF4444' : 'var(--accent)',
          borderRadius: 4, transition: 'width 0.3s ease',
        }} />
      </div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{
          fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16,
          color: low ? '#EF4444' : 'var(--ink)',
        }}>
          {remaining} / {total}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)' }}>
          Resets: {resetStr}
        </span>
      </div>
      {onTopup && (
        <button onClick={onTopup} style={{
          marginTop: 10, width: '100%', padding: '8px 0',
          background: 'var(--accent-soft)', color: 'var(--ink)',
          border: 'none', borderRadius: 'var(--radius-sm)',
          fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
          cursor: 'pointer',
        }}>
          Top up +200 credits — RM10
        </button>
      )}
    </div>
  )
}
