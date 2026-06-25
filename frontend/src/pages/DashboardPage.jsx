import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { ProfileMenu } from '../components/ProfileMenu'
import api from '../api/client'

const MODES = [
  { value: 'general', label: 'General' },
  { value: 'quantitative', label: 'Quantitative / Science' },
  { value: 'qualitative', label: 'Qualitative / Social Science' },
  { value: 'law', label: 'Law' },
  { value: 'medicine', label: 'Medicine / Health' },
]

export function DashboardPage() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const showSetPasswordNudge = searchParams.get('setup_password') === '1'
  const [nudgeDismissed, setNudgeDismissed] = useState(false)
  const [projects, setProjects] = useState([])
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newMode, setNewMode] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showStep0, setShowStep0] = useState(false)
  const [profileName, setProfileName] = useState('')
  const [profileIpt, setProfileIpt] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)
  const [newOutputTarget, setNewOutputTarget] = useState('thesis')
  const [newDegreeLevel, setNewDegreeLevel] = useState('master')
  const [newProposalStatus, setNewProposalStatus] = useState('belum')
  const [tier, setTier] = useState(null)
  const [profileError, setProfileError] = useState('')
  const [step0Success, setStep0Success] = useState(false)
  const [justCompletedStep0, setJustCompletedStep0] = useState(false)
  const [userName, setUserName] = useState('')
  const user = JSON.parse(localStorage.getItem('rhq_user') || '{}')

  useEffect(() => {
    Promise.all([
      api.get('/projects'),
      api.get('/account'),
    ]).then(([projRes, accRes]) => {
      setProjects(projRes.data)
      setLoading(false)
      setTier(accRes.data.tier)
      setUserName(accRes.data.name || '')
      if (!accRes.data.name) setShowStep0(true)
      const latest = projRes.data[0]  // ORDER BY created_at DESC dalam API
      if (latest) {
        if (latest.output_target) setNewOutputTarget(latest.output_target)
        if (latest.degree_level) setNewDegreeLevel(latest.degree_level)
        if (latest.proposal_status) setNewProposalStatus(latest.proposal_status)
      }
    })
  }, [])

  async function createProject(e) {
    e.preventDefault()
    setError('')
    try {
      const { data } = await api.post('/projects', {
        title: newTitle,
        research_mode: newMode,
        output_target: newOutputTarget,
        degree_level: newDegreeLevel,
        proposal_status: newProposalStatus,
      })
      setJustCompletedStep0(false)
      // Branch by proposal_status
      if (newProposalStatus === 'belum') {
        nav(`/project/${data.id}?mode=discovery`)
      } else {
        nav(`/project/${data.id}?mode=proposal_upload`)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create project.')
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
        <ProfileMenu user={user} tier={tier} userName={userName} />
      </header>

      {showSetPasswordNudge && !nudgeDismissed && (
        <div style={{
          background: '#FFF7ED', borderBottom: '1px solid #FED7AA',
          padding: '12px 24px', display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', flexShrink: 0,
        }}>
          <p style={{ margin: 0, fontSize: 14, color: '#C2410C' }}>
            Set a permanent password so you don't need to use email every time you log in.{' '}
            <a href="/app/account" style={{ color: '#C2410C', fontWeight: 600, textDecoration: 'underline' }}>
              Set it now →
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

      {showStep0 && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }}>
          <div style={{
            background: 'var(--card)', borderRadius: 'var(--radius-md)',
            padding: 32, width: '100%', maxWidth: 400,
            border: '1px solid var(--line)',
          }}>
            {step0Success ? (
              <>
                <p style={{ fontSize: 32, margin: '0 0 12px' }}>✓</p>
                <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, margin: '0 0 8px', fontSize: 22 }}>
                  Profile saved!
                </h2>
                <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 24px' }}>
                  Now create your first project.
                </p>
                <button
                  onClick={() => {
                    setShowStep0(false)
                    setStep0Success(false)
                    setJustCompletedStep0(true)
                    setCreating(true)
                  }}
                  style={{
                    width: '100%', padding: '12px', background: 'var(--accent)', color: 'var(--ink)',
                    border: 'none', borderRadius: 8, fontFamily: 'var(--font-heading)',
                    fontWeight: 700, fontSize: 15, cursor: 'pointer',
                  }}
                >
                  Create First Project →
                </button>
              </>
            ) : (
              <>
                <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, margin: '0 0 8px', fontSize: 22 }}>
                  Welcome to researcherHQ
                </h2>
                <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 24px' }}>
                  Tell us a little about yourself for a better experience.
                </p>
                <input
                  value={profileName}
                  onChange={e => { setProfileName(e.target.value); setProfileError('') }}
                  placeholder="Your full name"
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, marginBottom: 12, boxSizing: 'border-box' }}
                />
                <input
                  value={profileIpt}
                  onChange={e => { setProfileIpt(e.target.value); setProfileError('') }}
                  placeholder="University / Institution name"
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, marginBottom: profileError ? 8 : 20, boxSizing: 'border-box' }}
                />
                {profileError && (
                  <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 12px' }}>{profileError}</p>
                )}
                <button
                  disabled={!profileName.trim() || savingProfile}
                  onClick={async () => {
                    setSavingProfile(true)
                    setProfileError('')
                    try {
                      await api.patch('/account/profile', { name: profileName.trim(), institution: profileIpt.trim() })
                      setUserName(profileName.trim())
                      setStep0Success(true)
                    } catch (err) {
                      if (err.response?.status === 401) {
                        setProfileError('Please sign in again.')
                      } else if (!err.response) {
                        setProfileError('Failed to connect to server. Please try again.')
                      } else {
                        setProfileError('An error occurred. Please try again.')
                      }
                    } finally {
                      setSavingProfile(false)
                    }
                  }}
                  style={{
                    width: '100%', padding: '12px', background: 'var(--ink)', color: 'var(--bg)',
                    border: 'none', borderRadius: 8, fontFamily: 'var(--font-heading)',
                    fontWeight: 700, fontSize: 15, cursor: profileName.trim() ? 'pointer' : 'not-allowed',
                    opacity: profileName.trim() ? 1 : 0.5,
                  }}
                >
                  {savingProfile ? 'Saving...' : 'Continue →'}
                </button>
                <p style={{ textAlign: 'center', marginTop: 12, fontSize: 13, color: 'var(--ink-soft)' }}>
                  <button
                    type="button"
                    onClick={() => setShowStep0(false)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 13, textDecoration: 'underline', padding: 0 }}
                  >
                    Skip for now
                  </button>
                </p>
              </>
            )}
          </div>
        </div>
      )}

      <main style={{ maxWidth: 800, margin: '0 auto', padding: '40px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, margin: 0, fontSize: 24 }}>
            My Projects
          </h1>
          <button onClick={() => setCreating(true)} style={{
            padding: '10px 20px', background: 'var(--ink)', color: 'var(--bg)',
            border: 'none', borderRadius: 'var(--radius-sm)',
            fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 14, cursor: 'pointer',
          }}>
            + New Project
          </button>
        </div>

        {creating && (
          <form onSubmit={createProject} style={{
            background: 'var(--card)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-md)', padding: 24, marginBottom: 24,
          }}>
            {justCompletedStep0 && (
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-soft)', margin: '0 0 8px', letterSpacing: '0.04em' }}>
                Step 2 of 2 — Your Project
              </p>
            )}
            <h3 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 16px' }}>
              New Project
            </h3>
            <input value={newTitle} onChange={e => setNewTitle(e.target.value)}
              placeholder="e.g. Financial Literacy Among University Students" required
              style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, marginBottom: 12, boxSizing: 'border-box' }}
            />
            <select value={newMode} onChange={e => setNewMode(e.target.value)} required
              style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, marginBottom: 16, boxSizing: 'border-box' }}>
              <option value="" disabled>— Select research field —</option>
              {MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <div style={{ border: '1px solid var(--line)', borderRadius: 8, padding: '16px', marginBottom: 16 }}>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', margin: '0 0 12px' }}>
                Research Details
              </p>
              <div style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', marginBottom: 6 }}>
                  Degree Level
                </label>
                <select value={newDegreeLevel} onChange={e => setNewDegreeLevel(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, boxSizing: 'border-box' }}>
                  <option value="master">Master</option>
                  <option value="phd">PhD</option>
                  <option value="lain-lain">Other</option>
                </select>
              </div>
              <div style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', marginBottom: 6 }}>
                  Output Goal
                </label>
                <select value={newOutputTarget} onChange={e => setNewOutputTarget(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 8, fontFamily: 'var(--font-body)', fontSize: 15, boxSizing: 'border-box' }}>
                  <option value="thesis">Thesis</option>
                  <option value="article">Journal Article</option>
                  <option value="proposal">Proposal</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontFamily: 'var(--font-mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-soft)', marginBottom: 6 }}>
                  Proposal Status
                </label>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[
                    { value: 'belum', label: 'No proposal yet' },
                    { value: 'lulus', label: 'Already approved' },
                  ].map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setNewProposalStatus(opt.value)}
                      style={{
                        flex: 1, padding: '10px', border: `1px solid ${newProposalStatus === opt.value ? 'var(--accent)' : 'var(--line)'}`,
                        borderRadius: 8, background: newProposalStatus === opt.value ? 'var(--accent-soft)' : 'transparent',
                        fontFamily: 'var(--font-body)', fontSize: 14, cursor: 'pointer',
                        fontWeight: newProposalStatus === opt.value ? 700 : 400,
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 12px' }}>{error}</p>}
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" style={{ padding: '10px 20px', background: 'var(--accent)', color: 'var(--ink)', border: 'none', borderRadius: 8, fontWeight: 700, cursor: 'pointer' }}>
                Create Project
              </button>
              <button type="button" onClick={() => { setCreating(false); setError(''); setJustCompletedStep0(false) }}
                style={{ padding: '10px 20px', background: 'transparent', border: '1px solid var(--line)', borderRadius: 8, cursor: 'pointer' }}>
                Cancel
              </button>
            </div>
          </form>
        )}

        {loading ? (
          <p style={{ color: 'var(--ink-soft)' }}>Loading projects...</p>
        ) : projects.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0' }}>
            <p style={{ color: 'var(--ink-soft)', fontSize: 16 }}>No projects yet.</p>
            <p style={{ color: 'var(--ink-soft)', fontSize: 14 }}>Click "+ New Project" to get started.</p>
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
