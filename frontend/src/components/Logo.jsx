function RMark({ height }) {
  return (
    <img
      src={`${import.meta.env.BASE_URL}logo-researcherhq-v1.svg`}
      alt="ResearcherHQ"
      style={{ height, width: 'auto', display: 'block' }}
    />
  )
}

export function Logo({ size = 'md', dark = false }) {
  const sizes = {
    sm: { mark: 24, badge: 11, gap: 6, pad: '4px 8px', radius: 6 },
    md: { mark: 34, badge: 14, gap: 8, pad: '5px 10px', radius: 7 },
    lg: { mark: 52, badge: 18, gap: 12, pad: '7px 14px', radius: 8 },
  }
  const s = sizes[size]

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: s.gap }}>
      <span style={{ color: dark ? 'var(--bg)' : 'var(--ink)', lineHeight: 1, display: 'inline-flex' }}>
        <RMark height={s.mark} />
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
  return (
    <div style={{
      width: size, height: size,
      borderRadius: radius,
      background: alt ? 'var(--accent)' : 'var(--ink)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <span style={{ color: alt ? 'var(--ink)' : 'var(--accent)', display: 'inline-flex' }}>
        <RMark height={Math.round(size * 0.55)} />
      </span>
    </div>
  )
}
