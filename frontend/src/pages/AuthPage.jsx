import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { TurnstileWidget } from '../components/TurnstileWidget'
import api from '../api/client'

export function AuthPage() {
  const nav = useNavigate()
  // 'login' = default direct login, 'request' = request OTP email, 'password-after-request' = enter emailed password
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
      setError(err.response?.data?.detail || 'Emel atau kata laluan tidak sah.')
    }
    setLoading(false)
  }

  async function handleRequestPassword(e) {
    e.preventDefault()
    if (!turnstileToken) {
      setError('Sila lengkapkan verifikasi sebelum hantar.')
      return
    }
    setLoading(true); setError('')
    try {
      await api.post('/auth/request-password', { email, turnstile_token: turnstileToken })
      setInfo('Kata laluan telah dihantar ke emel anda.')
      setMode('password-after-request')
    } catch (err) {
      setError(err.response?.data?.detail || 'Ralat berlaku.')
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
      setError(err.response?.data?.detail || 'Kata laluan salah.')
    }
    setLoading(false)
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)', padding: 24,
    }}>
      <div style={{ marginBottom: 32 }}><Logo size="lg" /></div>
      <div style={{
        background: 'var(--card)', border: '1px solid var(--line)',
        borderRadius: 'var(--radius-lg)', padding: '40px 48px',
        width: '100%', maxWidth: 400,
      }}>
        {mode === 'login' && (
          <form onSubmit={handleDirectLogin}>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px' }}>Log Masuk</h2>
            <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 24px' }}>
              Masukkan emel dan kata laluan anda.
            </p>
            <input
              type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="emel@universiti.edu.my" required
              style={inputStyle}
            />
            <input
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="Kata laluan" required
              style={inputStyle}
            />
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '8px 0 0' }}>{error}</p>}
            <button type="submit" disabled={loading} style={btnStyle}>
              {loading ? 'Log masuk...' : 'Log Masuk →'}
            </button>
            <button
              type="button"
              onClick={() => { setMode('request'); setError(''); setPassword('') }}
              style={{ ...btnStyle, background: 'transparent', color: 'var(--ink-soft)', border: '1px solid var(--line)', marginTop: 8 }}
            >
              Lupa kata laluan / pertama kali log masuk?
            </button>
          </form>
        )}

        {mode === 'request' && (
          <form onSubmit={handleRequestPassword}>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px' }}>Hantar Kata Laluan</h2>
            <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 24px' }}>
              Kami akan hantar kata laluan ke emel anda.
            </p>
            <input
              type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="emel@universiti.edu.my" required
              style={inputStyle}
            />
            <TurnstileWidget onVerify={setTurnstileToken} onExpire={() => setTurnstileToken('')} />
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '8px 0 0' }}>{error}</p>}
            <button type="submit" disabled={loading || !turnstileToken} style={btnStyle}>
              {loading ? 'Menghantar...' : 'Hantar Kata Laluan →'}
            </button>
            <button
              type="button"
              onClick={() => { setMode('login'); setError('') }}
              style={{ ...btnStyle, background: 'transparent', color: 'var(--ink-soft)', marginTop: 8 }}
            >
              ← Kembali
            </button>
          </form>
        )}

        {mode === 'password-after-request' && (
          <form onSubmit={handleLoginAfterRequest}>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px' }}>Masukkan Kata Laluan</h2>
            {info && <p style={{ color: '#16A34A', fontSize: 13, margin: '0 0 16px', background: '#F0FDF4', padding: '8px 12px', borderRadius: 8 }}>{info}</p>}
            <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 16px' }}>
              Emel: <strong>{email}</strong>
            </p>
            <input
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="Kata laluan dari emel" required
              style={inputStyle}
            />
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '8px 0 0' }}>{error}</p>}
            <button type="submit" disabled={loading} style={btnStyle}>
              {loading ? 'Log masuk...' : 'Log Masuk →'}
            </button>
            <button
              type="button"
              onClick={() => { setMode('request'); setInfo(''); setTurnstileToken(''); setPassword('') }}
              style={{ ...btnStyle, background: 'transparent', color: 'var(--ink-soft)', marginTop: 8 }}
            >
              ← Guna emel lain
            </button>
          </form>
        )}
      </div>
      <p style={{ marginTop: 24, color: 'var(--ink-soft)', fontSize: 13, textAlign: 'center' }}>
        Workspace penyelidikan untuk postgrad Malaysia
      </p>
    </div>
  )
}

const inputStyle = {
  width: '100%', padding: '12px 14px',
  border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
  fontFamily: 'var(--font-body)', fontSize: 15, color: 'var(--ink)',
  background: 'var(--bg)', outline: 'none', marginBottom: 12,
  boxSizing: 'border-box',
}

const btnStyle = {
  width: '100%', padding: '12px 0',
  background: 'var(--ink)', color: 'var(--bg)',
  border: 'none', borderRadius: 'var(--radius-sm)',
  fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15,
  cursor: 'pointer', marginTop: 4, display: 'block',
}
