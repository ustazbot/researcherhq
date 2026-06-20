import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { ProfileMenu } from '../components/ProfileMenu'
import api from '../api/client'

const MODES = [
  { value: 'general', label: 'Umum' },
  { value: 'quantitative', label: 'Kuantitatif / Sains' },
  { value: 'qualitative', label: 'Kualitatif / Sains Sosial' },
  { value: 'law', label: 'Undang-undang' },
  { value: 'medicine', label: 'Perubatan / Kesihatan' },
]

export function DashboardPage() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const showSetPasswordNudge = searchParams.get('setup_password') === '1'
  const [nudgeDismissed, setNudgeDismissed] = useState(false)
  const [projects, setProjects] = useState([])
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newMode, setNewMode] = useState('general')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const user = JSON.parse(localStorage.getItem('rhq_user') || '{}')

  useEffect(() => {
    api.get('/projects').then(r => { setProjects(r.data); setLoading(false) })
  }, [])

  async function createProject(e) {
    e.preventDefault()
    setError('')
    try {
      const { data } = await api.post('/projects', { title: newTitle, research_mode: newMode })
      nav(`/project/${data.id}`)
    } catch (err) {
      setError(err.response?.data?.detail || 'Gagal cipta projek.')
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <header style={{
        borderBottom: '1px solid var(--line)', padding: '0 24px',
        height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: 'var(--card)',
      }}>
        <Logo size="md" />
        <ProfileMenu user={user} />
      </header>

      {showSetPasswordNudge && !nudgeDismissed && (
        <div style={{
          background: '#FFF7ED', borderBottom: '1px solid #FED7AA',
          padding: '12px 24px', display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', flexShrink: 0,
        }}>
          <p style={{ margin: 0, fontSize: 14, color: '#C2410C' }}>
            Tetapkan kata laluan tetap supaya anda tidak perlu emel setiap kali log masuk.{' '}
            <a href="/app/account" style={{ color: '#C2410C', fontWeight: 600, textDecoration: 'underline' }}>
              Tetapkan sekarang →
            </a>
          </p>
          <button
            onClick={() => setNudgeDismissed(true)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#C2410C', fontSize: 18, padding: '0 4px' }}
          >
            ×
          </button>
        </div>
      )}

      <main style={{ maxWidth: 800, margin: '0 auto', padding: '40px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, margin: 0, fontSize: 24 }}>
            Projek Saya
          </h1>
          <button onClick={() => setCreating(true)} style={{
            padding: '10px 20px', background: 'var(--ink)', color: 'var(--bg)',
            border: 'none', borderRadius: 'var(--radius-sm)',
            fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14, cursor: 'pointer',
          }}>
            + Projek Baru
          </button>
        </div>

        {creating && (
          <form onSubmit={createProject} style={{
            background: 'var(--card)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-md)', padding: 24, marginBottom: 24,
          }}>
            <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 16px' }}>
              Projek Baru
            </h3>
            <input value={newTitle} onChange={e => setNewTitle(e.target.value)}
              placeholder="Tajuk projek / tesis" required
              style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, marginBottom: 12 }}
            />
            <select value={newMode} onChange={e => setNewMode(e.target.value)}
              style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, marginBottom: 16 }}>
              {MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 12px' }}>{error}</p>}
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" style={{ padding: '10px 20px', background: 'var(--accent)', color: 'var(--ink)', border: 'none', borderRadius: 8, fontWeight: 700, cursor: 'pointer' }}>
                Cipta Projek
              </button>
              <button type="button" onClick={() => { setCreating(false); setError('') }}
                style={{ padding: '10px 20px', background: 'transparent', border: '1px solid var(--line)', borderRadius: 8, cursor: 'pointer' }}>
                Batal
              </button>
            </div>
          </form>
        )}

        {loading ? (
          <p style={{ color: 'var(--ink-soft)' }}>Memuatkan projek...</p>
        ) : projects.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0' }}>
            <p style={{ color: 'var(--ink-soft)', fontSize: 16 }}>Tiada projek lagi.</p>
            <p style={{ color: 'var(--ink-soft)', fontSize: 14 }}>Klik "Projek Baru" untuk mulakan.</p>
          </div>
        ) : (
          <div style={{ display: 'grid', gap: 12 }}>
            {projects.map(p => (
              <div key={p.id} onClick={() => nav(`/project/${p.id}`)}
                style={{
                  background: 'var(--card)', border: '1px solid var(--line)',
                  borderRadius: 'var(--radius-md)', padding: '20px 24px',
                  cursor: 'pointer', transition: 'border-color 0.15s',
                }}
                onMouseOver={e => e.currentTarget.style.borderColor = 'var(--accent)'}
                onMouseOut={e => e.currentTarget.style.borderColor = 'var(--line)'}
              >
                <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 4px', fontSize: 18 }}>
                  {p.title}
                </h3>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11,
                  background: 'var(--accent-soft)', color: 'var(--ink)',
                  padding: '2px 8px', borderRadius: 4,
                }}>
                  {MODES.find(m => m.value === p.research_mode)?.label || p.research_mode}
                </span>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
