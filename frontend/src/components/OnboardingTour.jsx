import { useEffect, useLayoutEffect, useState } from 'react'

const SEEN_KEY = 'rhq_tour_seen_v1'

const STEPS = [
  {
    targetId: 'rhq-tour-sources',
    copy: 'Upload your reference articles, proposal, and notes here. This is what the AI reads — answers are grounded in your own documents, not generic knowledge.',
  },
  {
    targetId: 'rhq-tour-chat-input',
    copy: 'Ask questions about your sources. Every answer traces back to the exact document and page — no guessing, no made-up citations. This is the core difference from ChatGPT.',
  },
  {
    targetId: null,
    illustration: true,
    copy: 'Like an answer? Send it to your chapter, review it, then Accept to add it to your thesis draft — you stay in control of what goes in.',
  },
  {
    targetId: 'rhq-tour-thesis',
    copy: 'This is where your chapters live — assign AI-generated content to each one and export a complete draft.',
    proCopy: ' This is what a complete research workflow looks like on Pro.',
  },
]

function SendToEditorIllustration() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, margin: '12px 0',
      padding: 12, background: 'var(--bg)', borderRadius: 'var(--radius-md)', border: '1px solid var(--line)',
    }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)', border: '1px solid var(--line)', borderRadius: 4, padding: '3px 8px' }}>
        → Send to Editor
      </span>
      <span style={{ color: 'var(--ink-soft)' }}>→</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)', border: '1px solid var(--accent)', borderRadius: 4, padding: '3px 8px' }}>
        Accept
      </span>
    </div>
  )
}

export function OnboardingTour({ active, isPro }) {
  const [seen, setSeen] = useState(() => !!localStorage.getItem(SEEN_KEY))
  const [step, setStep] = useState(0)
  const [rect, setRect] = useState(null)

  const visible = active && !seen
  const current = STEPS[step]

  useLayoutEffect(() => {
    if (!visible) return
    const recalc = () => {
      const el = current.targetId && document.getElementById(current.targetId)
      setRect(el ? el.getBoundingClientRect() : null)
    }
    recalc()
    window.addEventListener('resize', recalc)
    return () => window.removeEventListener('resize', recalc)
  }, [visible, current])

  // ponytail: re-run on next paint so panel layout has settled before measuring
  useEffect(() => {
    if (!visible) return
    const id = requestAnimationFrame(() => {
      const el = current.targetId && document.getElementById(current.targetId)
      setRect(el ? el.getBoundingClientRect() : null)
    })
    return () => cancelAnimationFrame(id)
  }, [visible, step, current])

  if (!visible) return null

  function finish() {
    localStorage.setItem(SEEN_KEY, '1')
    setSeen(true)
  }

  const cardStyle = {
    background: 'var(--card)', border: '1px solid var(--line)', borderRadius: 'var(--radius-md)',
    padding: 20, width: 320, boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
  }

  const cardPosition = rect
    ? {
        position: 'fixed',
        top: Math.min(rect.bottom + 12, window.innerHeight - 220),
        left: Math.min(Math.max(rect.left, 16), window.innerWidth - 336),
      }
    : { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1500 }}>
      {rect ? (
        <div style={{
          position: 'fixed',
          top: rect.top - 6, left: rect.left - 6, width: rect.width + 12, height: rect.height + 12,
          border: '2px solid var(--accent)', borderRadius: 'var(--radius-md)',
          boxShadow: '0 0 0 9999px rgba(0,0,0,0.55)',
          pointerEvents: 'none',
        }} />
      ) : (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)' }} />
      )}

      <div style={{ ...cardStyle, ...cardPosition }}>
        <p style={{ margin: '0 0 8px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Step {step + 1} of {STEPS.length}
        </p>
        {current.illustration && <SendToEditorIllustration />}
        <p style={{ margin: 0, fontSize: 14, color: 'var(--ink)', lineHeight: 1.5 }}>
          {current.copy}{!isPro && current.proCopy}
        </p>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
          <button
            onClick={finish}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 13, textDecoration: 'underline', padding: 0 }}
          >
            Skip
          </button>
          <button
            onClick={() => (step < STEPS.length - 1 ? setStep(step + 1) : finish())}
            style={{
              background: 'var(--accent)', color: 'var(--ink)', border: 'none', borderRadius: 'var(--radius-md)',
              padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer',
            }}
          >
            {step < STEPS.length - 1 ? 'Next' : 'Got it'}
          </button>
        </div>
      </div>
    </div>
  )
}
