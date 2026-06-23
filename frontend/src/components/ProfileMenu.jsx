import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'

export function ProfileMenu({ user, tier: tierProp, userName }) {
  const [open, setOpen] = useState(false)
  const [credits, setCredits] = useState(null)
  const [topping, setTopping] = useState(false)
  const tier = tierProp ?? credits?.tier ?? user?.tier
  const nav = useNavigate()
  const ref = useRef()

  useEffect(() => {
    function close(e) { if (!ref.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  async function toggle() {
    if (!open && !credits) {
      try { const { data } = await api.get('/credits'); setCredits(data) } catch {}
    }
    setOpen(!open)
  }

  function logout() {
    localStorage.removeItem('rhq_token')
    localStorage.removeItem('rhq_user')
    nav('/auth')
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button onClick={toggle} style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 12px', background: 'var(--bg)',
        border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
        cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 14,
      }}>
        <span style={{
          width: 28, height: 28, borderRadius: '50%',
          background: 'var(--ink)', color: 'var(--bg)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 12,
        }}>
          {userName?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || 'U'}
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 11,
          background: tier === 'pro' ? 'var(--accent)' : 'var(--line)',
          padding: '2px 6px', borderRadius: 4,
        }}>
          {tier === 'pro' ? 'PRO' : 'FREE'}
        </span>
      </button>

      {open && (
        <div style={{
          position: 'absolute', right: 0, top: '100%', marginTop: 8,
          background: 'var(--card)', border: '1px solid var(--line)',
          borderRadius: 'var(--radius-md)', padding: 8,
          minWidth: 220, zIndex: 100, boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
        }}>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--line)', marginBottom: 4 }}>
            {userName && <p style={{ margin: '0 0 2px', fontSize: 13, fontWeight: 600 }}>{userName}</p>}
            <p style={{ margin: 0, fontSize: 13, fontWeight: 500, color: userName ? 'var(--ink-soft)' : 'var(--ink)' }}>{user?.email}</p>
            {credits && (
              <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--ink-soft)', fontFamily: 'var(--font-mono)' }}>
                Baki Kredit Kajian: {credits.kredit_remaining}
              </p>
            )}
          </div>
          {[
            { label: 'Tetapan Akaun', action: () => nav('/account') },
            { label: 'Laporkan Isu', action: () => nav('/support') },
          ].map(item => (
            <button key={item.label} onClick={item.action} style={menuItemStyle}>
              {item.label}
            </button>
          ))}
          {tier === 'pro' && (
            <button
              onClick={async () => {
                setTopping(true)
                try {
                  const { data } = await api.post('/billing/topup/initiate')
                  window.location.href = data.payment_url
                } catch {
                  alert('Gagal memulakan topup. Sila cuba lagi.')
                  setTopping(false)
                }
              }}
              disabled={topping}
              style={{ ...menuItemStyle, color: 'var(--accent)', fontWeight: 600, opacity: topping ? 0.7 : 1 }}
            >
              {topping ? 'Memproses...' : 'Topup +200 kredit — RM10'}
            </button>
          )}
          <button onClick={logout} style={{ ...menuItemStyle, color: '#EF4444', borderTop: '1px solid var(--line)', marginTop: 4 }}>
            Log Keluar
          </button>
        </div>
      )}
    </div>
  )
}

const menuItemStyle = {
  display: 'block', width: '100%', padding: '8px 12px',
  background: 'transparent', border: 'none', borderRadius: 6,
  fontFamily: 'var(--font-body)', fontSize: 14, textAlign: 'left',
  cursor: 'pointer', color: 'var(--ink)',
}
