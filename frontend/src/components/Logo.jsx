export function Logo({ size = 'md', dark = false }) {
  const sizes = {
    sm: { word: 20, badge: 11, gap: 6, pad: '4px 8px', radius: 6 },
    md: { word: 28, badge: 14, gap: 8, pad: '5px 10px', radius: 7 },
    lg: { word: 44, badge: 18, gap: 12, pad: '7px 14px', radius: 8 },
  }
  const s = sizes[size]

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: s.gap }}>
      <span style={{
        fontFamily: 'var(--font-heading)',
        fontWeight: 700,
        fontSize: s.word,
        color: dark ? 'var(--bg)' : 'var(--ink)',
        lineHeight: 1,
      }}>
        Researcher
      </span>
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontWeight: 500,
        fontSize: s.badge,
        letterSpacing: '0.05em',
        background: dark ? 'var(--accent)' : 'var(--ink)',
        color: dark ? 'var(--ink)' : 'var(--bg)',
        padding: s.pad,
        borderRadius: s.radius,
        transform: 'translateY(-2px)',
        lineHeight: 1,
      }}>
        HQ
      </span>
    </div>
  )
}

export function AppIcon({ size = 96, alt = false }) {
  const radius = Math.round(size * 0.23)
  const fontSize = Math.round(size * 0.31)
  return (
    <div style={{
      width: size, height: size,
      borderRadius: radius,
      background: alt ? 'var(--accent)' : 'var(--ink)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <span style={{
        fontFamily: 'var(--font-heading)',
        fontWeight: 800,
        fontSize,
        color: alt ? 'var(--ink)' : 'var(--accent)',
        letterSpacing: '0.01em',
      }}>
        HQ
      </span>
    </div>
  )
}
