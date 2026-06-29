import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { TurnstileWidget } from '../components/TurnstileWidget'
import api from '../api/client'

export function AuthPage() {
  const nav = useNavigate()
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [turnstileToken, setTurnstileToken] = useState('')

  async function handleDirectLogin(e) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const { data } = await api.post('/auth/login', { email, password })
      localStorage.setItem('rhq_token', data.access_token)
      localStorage.setItem('rhq_user', JSON.stringify(data.user))
      nav('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Incorrect email or password.')
    }
    setLoading(false)
  }

  async function handleRequestPassword(e) {
    e.preventDefault()
    if (!turnstileToken) {
      setError('Complete the verification before continuing.')
      return
    }
    setLoading(true); setError('')
    try {
      await api.post('/auth/request-password', { email, turnstile_token: turnstileToken })
      setInfo('Password sent. Check your inbox and spam folder.')
      setMode('password-after-request')
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong. Try again.')
      setTurnstileToken('')
    }
    setLoading(false)
  }

  async function handleLoginAfterRequest(e) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const { data } = await api.post('/auth/login', { email, password })
      localStorage.setItem('rhq_token', data.access_token)
      localStorage.setItem('rhq_user', JSON.stringify(data.user))
      nav('/?setup_password=1')
    } catch (err) {
      setError(err.response?.data?.detail || 'Incorrect password. Check your email and try again.')
    }
    setLoading(false)
  }

  return (
    <div style={pageStyle}>
      <div style={wrapStyle}>

        {/* Logo */}
        <Logo size="lg" />

        {/* Card */}
        <div style={cardStyle}>

          {/* STATE: login */}
          {mode === 'login' && (
            <form onSubmit={handleDirectLogin}>
              <h2 style={titleStyle}>Welcome back</h2>
              <p style={subStyle}>Enter your email and password to continue.</p>

              <label style={labelStyle}>Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="name@university.edu.my"
                required
                style={inputStyle}
              />

              <label style={labelStyle}>Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Your password"
                required
                style={inputStyle}
              />

              <div style={{ textAlign: 'right', marginTop: -6, marginBottom: 18 }}>
                <button
                  type="button"
                  onClick={() => { setMode('request'); setError(''); setPassword('') }}
                  style={forgotStyle}
                >
                  Forgot password?
                </button>
              </div>

              {error && <p style={errorStyle}>{error}</p>}

              <button type="submit" disabled={loading} style={btnPrimaryStyle}>
                {loading ? 'Logging in...' : 'Log in'}
              </button>

              <div style={dividerStyle}>
                <div style={dividerLineStyle} />
                <span style={dividerTextStyle}>new to ResearcherHQ?</span>
                <div style={dividerLineStyle} />
              </div>

              <button
                type="button"
                onClick={() => { setMode('request'); setError('') }}
                style={btnSecondaryStyle}
              >
                Create a free account
              </button>
            </form>
          )}

          {/* STATE: request (new user or forgot password) */}
          {mode === 'request' && (
            <form onSubmit={handleRequestPassword}>
              <h2 style={titleStyle}>Get started</h2>
              <p style={subStyle}>
                Enter your email and we'll send you a password to log in.
                Free to start — no credit card needed.
              </p>

              <label style={labelStyle}>Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="name@university.edu.my"
                required
                style={inputStyle}
              />

              <TurnstileWidget
                onVerify={setTurnstileToken}
                onExpire={() => setTurnstileToken('')}
              />

              {error && <p style={errorStyle}>{error}</p>}

              <button
                type="submit"
                disabled={loading || !turnstileToken}
                style={{ ...btnPrimaryStyle, opacity: (!turnstileToken || loading) ? 0.6 : 1 }}
              >
                {loading ? 'Sending...' : 'Send login password'}
              </button>

              <div style={dividerStyle}>
                <div style={dividerLineStyle} />
                <span style={dividerTextStyle}>already have an account?</span>
                <div style={dividerLineStyle} />
              </div>

              <button
                type="button"
                onClick={() => { setMode('login'); setError('') }}
                style={btnSecondaryStyle}
              >
                Log in instead
              </button>
            </form>
          )}

          {/* STATE: enter emailed password */}
          {mode === 'password-after-request' && (
            <form onSubmit={handleLoginAfterRequest}>
              <button
                type="button"
                onClick={() => { setMode('request'); setInfo(''); setTurnstileToken(''); setPassword('') }}
                style={backLinkStyle}
              >
                ← Use a different email
              </button>

              <h2 style={titleStyle}>Check your email</h2>
              <p style={subStyle}>We sent a temporary password to:</p>

              <div style={emailChipStyle}>
                <span style={{ color: 'var(--ink-soft)', fontSize: 13 }}>✉</span>
                <span style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 500 }}>{email}</span>
              </div>

              {info && (
                <div style={infoBoxStyle}>
                  {info}
                </div>
              )}

              <label style={labelStyle}>Temporary password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Paste from your email"
                required
                style={inputStyle}
              />

              {error && <p style={errorStyle}>{error}</p>}

              <button type="submit" disabled={loading} style={btnPrimaryStyle}>
                {loading ? 'Logging in...' : 'Continue'}
              </button>

              <p style={{ ...subStyle, textAlign: 'center', marginTop: 14, marginBottom: 0, fontSize: 12 }}>
                You can set a permanent password after logging in.
              </p>
            </form>
          )}

        </div>

        {/* Footer note */}
        <p style={footNoteStyle}>
          AI research workspace for Malaysian postgraduate students.
        </p>

      </div>
    </div>
  )
}

/* ── Styles ── */
const pageStyle = {
  minHeight: '100vh',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'var(--bg)',
  padding: '24px 16px',
}

const wrapStyle = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  gap: 28,
  width: '100%',
  maxWidth: 420,
}

const cardStyle = {
  background: 'var(--card)',
  border: '1px solid var(--line)',
  borderRadius: 'var(--radius-lg)',
  padding: '36px 40px',
  width: '100%',
}

const titleStyle = {
  fontFamily: 'var(--font-heading)',
  fontSize: 20,
  fontWeight: 700,
  color: 'var(--ink)',
  margin: '0 0 6px',
  letterSpacing: '-0.3px',
}

const subStyle = {
  fontSize: 13,
  color: 'var(--ink-soft)',
  margin: '0 0 22px',
  lineHeight: 1.55,
}

const labelStyle = {
  display: 'block',
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--ink-soft)',
  marginBottom: 5,
  letterSpacing: '0.01em',
}

const inputStyle = {
  width: '100%',
  padding: '11px 13px',
  border: '1px solid var(--line)',
  borderRadius: 'var(--radius-sm)',
  fontFamily: 'var(--font-body)',
  fontSize: 14,
  color: 'var(--ink)',
  background: 'var(--bg)',
  outline: 'none',
  marginBottom: 14,
  boxSizing: 'border-box',
  display: 'block',
}

const forgotStyle = {
  background: 'none',
  border: 'none',
  padding: 0,
  fontSize: 12,
  color: 'var(--ink-soft)',
  cursor: 'pointer',
  textDecoration: 'underline',
  textUnderlineOffset: 3,
  fontFamily: 'var(--font-body)',
}

const errorStyle = {
  color: '#EF4444',
  fontSize: 13,
  margin: '0 0 12px',
  lineHeight: 1.45,
}

const btnPrimaryStyle = {
  width: '100%',
  padding: '12px 0',
  background: 'var(--ink)',
  color: 'var(--bg)',
  border: 'none',
  borderRadius: 'var(--radius-sm)',
  fontFamily: 'var(--font-heading)',
  fontWeight: 700,
  fontSize: 14,
  cursor: 'pointer',
  display: 'block',
}

const btnSecondaryStyle = {
  width: '100%',
  padding: '11px 0',
  background: 'transparent',
  color: 'var(--ink-soft)',
  border: '1px solid var(--line)',
  borderRadius: 'var(--radius-sm)',
  fontFamily: 'var(--font-heading)',
  fontWeight: 600,
  fontSize: 14,
  cursor: 'pointer',
  display: 'block',
}

const dividerStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  margin: '18px 0',
}

const dividerLineStyle = {
  flex: 1,
  height: 1,
  background: 'var(--line)',
}

const dividerTextStyle = {
  fontSize: 12,
  color: '#aaa',
  whiteSpace: 'nowrap',
}

const backLinkStyle = {
  background: 'none',
  border: 'none',
  padding: 0,
  fontSize: 13,
  color: 'var(--ink-soft)',
  cursor: 'pointer',
  fontFamily: 'var(--font-body)',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  marginBottom: 18,
}

const emailChipStyle = {
  background: 'var(--bg)',
  border: '1px solid var(--line)',
  borderRadius: 'var(--radius-sm)',
  padding: '10px 13px',
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginBottom: 14,
}

const infoBoxStyle = {
  background: '#F0FDF4',
  border: '1px solid #BBF7D0',
  borderRadius: 'var(--radius-sm)',
  padding: '10px 13px',
  fontSize: 13,
  color: '#166534',
  marginBottom: 16,
  lineHeight: 1.5,
}

const footNoteStyle = {
  fontSize: 12,
  color: '#aaa',
  textAlign: 'center',
  lineHeight: 1.6,
}
