import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'

export function AccountSettingsPage() {
  const nav = useNavigate()
  const [account, setAccount] = useState(null)
  const [deleteStep, setDeleteStep] = useState(0) // 0=idle, 1=confirm modal
  const [deleteInput, setDeleteInput] = useState('')
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [error, setError] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [pwLoading, setPwLoading] = useState(false)
  const [pwSuccess, setPwSuccess] = useState('')
  const [pwError, setPwError] = useState('')
  const [profileName, setProfileName] = useState('')
  const [profileIpt, setProfileIpt] = useState('')
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileSuccess, setProfileSuccess] = useState('')
  const [profileError, setProfileError] = useState('')

  useEffect(() => {
    api.get('/account').then(r => {
      setAccount(r.data)
      setProfileName(r.data.name || '')
      setProfileIpt(r.data.institution || '')
    }).catch(() => setError('Gagal muatkan maklumat akaun.'))
  }, [])

  async function handleSetPassword(e) {
    e.preventDefault()
    setPwError('')
    setPwSuccess('')
    if (newPassword.length < 8) {
      setPwError('Kata laluan mesti sekurang-kurangnya 8 aksara.')
      return
    }
    if (newPassword !== confirmPassword) {
      setPwError('Kata laluan tidak sepadan.')
      return
    }
    setPwLoading(true)
    try {
      const { data } = await api.post('/auth/set-password', { new_password: newPassword })
      setPwSuccess(data.message)
      setAccount(prev => ({ ...prev, password_is_permanent: 1 }))
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setPwError(err.response?.data?.detail || 'Gagal tetapkan kata laluan. Cuba lagi.')
    }
    setPwLoading(false)
  }

  async function handleDeleteAccount() {
    if (deleteInput !== 'PADAM') return
    setDeleteLoading(true)
    setDeleteError('')
    try {
      await api.delete('/account')
      localStorage.removeItem('rhq_token')
      localStorage.removeItem('rhq_user')
      nav('/auth')
    } catch (err) {
      setDeleteError(err.response?.data?.detail || 'Gagal padam akaun. Cuba lagi.')
      setDeleteLoading(false)
    }
  }

  if (error) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <p style={{ color: '#EF4444' }}>{error}</p>
    </div>
  )

  if (!account) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <p style={{ color: 'var(--ink-soft)' }}>Memuatkan...</p>
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', padding: '40px 24px' }}>
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <button onClick={() => nav('/')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 14, marginBottom: 24, padding: 0 }}>
          ← Back to Dashboard
        </button>
        <h1 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 32px' }}>
          Account Settings
        </h1>

        {/* Maklumat Akaun */}
        <section style={sectionStyle}>
          <h2 style={sectionHeadingStyle}>Account Info</h2>
          <div style={rowStyle}>
            <span style={labelStyle}>Email</span>
            <span style={valueStyle}>{account.email}</span>
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Plan</span>
            <span style={{
              ...valueStyle,
              background: account.tier === 'pro' ? 'var(--accent)' : 'var(--line)',
              padding: '2px 8px', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 12,
            }}>
              {account.tier === 'pro' ? 'PRO' : 'FREE'}
            </span>
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Research Credits Balance</span>
            <span style={valueStyle}>{account.kredit_remaining} / {account.kredit_total} credits</span>
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Credits Reset</span>
            <span style={valueStyle}>{account.reset_date}</span>
          </div>
        </section>

        {/* Langganan */}
        <section style={sectionStyle}>
          <h2 style={sectionHeadingStyle}>Subscription</h2>
          {account.tier === 'pro' ? (
            <p style={{ fontSize: 14, color: 'var(--ink-soft)', margin: 0 }}>
              Untuk batalkan langganan Pro, hubungi <strong>support@researcherhq.com</strong>
            </p>
          ) : (
            <button
              onClick={async () => {
                try {
                  const { data } = await api.post('/billing/upgrade/initiate')
                  window.location.href = data.payment_url
                } catch {
                  alert('Gagal memulakan pembayaran. Sila cuba lagi.')
                }
              }}
              style={{ padding: '10px 20px', background: 'var(--accent)', color: 'var(--ink)', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, cursor: 'pointer' }}
            >
              Upgrade to Pro — RM39/month
            </button>
          )}
        </section>

        {/* Profil Anda */}
        <section style={sectionStyle}>
          <h2 style={sectionHeadingStyle}>Your Profile</h2>
          <input
            value={profileName}
            onChange={e => { setProfileName(e.target.value); setProfileSuccess(''); setProfileError('') }}
            placeholder="Nama penuh"
            style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)', marginBottom: 10, boxSizing: 'border-box' }}
          />
          <input
            value={profileIpt}
            onChange={e => { setProfileIpt(e.target.value); setProfileSuccess(''); setProfileError('') }}
            placeholder="University / Institution name"
            style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)', marginBottom: 10, boxSizing: 'border-box' }}
          />
          {profileError && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 10px' }}>{profileError}</p>}
          {profileSuccess && <p style={{ color: '#16A34A', fontSize: 13, margin: '0 0 10px' }}>{profileSuccess}</p>}
          <button
            disabled={profileLoading || !profileName.trim()}
            onClick={async () => {
              setProfileLoading(true)
              setProfileError('')
              setProfileSuccess('')
              try {
                await api.patch('/account/profile', { name: profileName.trim(), institution: profileIpt.trim() })
                setProfileSuccess('Profil dikemaskini ✓')
              } catch (err) {
                if (err.response?.status === 401) {
                  setProfileError('Sila log masuk semula.')
                } else if (!err.response) {
                  setProfileError('Gagal sambung ke pelayan. Cuba semula.')
                } else {
                  setProfileError('Ralat berlaku. Sila cuba semula.')
                }
              } finally {
                setProfileLoading(false)
              }
            }}
            style={{ padding: '10px 20px', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, cursor: 'pointer', opacity: profileName.trim() ? 1 : 0.5 }}
          >
            {profileLoading ? 'Saving...' : 'Save Profile'}
          </button>
        </section>

        {/* Tukar Kata Laluan */}
        <section style={sectionStyle}>
          <h2 style={sectionHeadingStyle}>Change Password</h2>
          {!account.password_is_permanent && (
            <div style={{ background: '#FFF7ED', border: '1px solid #FED7AA', borderRadius: 8, padding: '12px 16px', marginBottom: 16 }}>
              <p style={{ fontSize: 13, color: '#C2410C', margin: 0 }}>
                Anda belum tetapkan kata laluan tetap. Tetapkan sekarang supaya tak perlu emel setiap kali log masuk.
              </p>
            </div>
          )}
          <form onSubmit={handleSetPassword}>
            <input
              type="password"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              placeholder="Kata Laluan Baharu (min. 8 aksara)"
              style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)', marginBottom: 10, boxSizing: 'border-box' }}
            />
            <input
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              placeholder="Sahkan Kata Laluan Baharu"
              style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)', marginBottom: 10, boxSizing: 'border-box' }}
            />
            {pwError && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 10px' }}>{pwError}</p>}
            {pwSuccess && <p style={{ color: '#16A34A', fontSize: 13, margin: '0 0 10px' }}>{pwSuccess}</p>}
            <button
              type="submit"
              disabled={pwLoading || !newPassword || !confirmPassword}
              style={{ padding: '10px 20px', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, cursor: 'pointer' }}
            >
              {pwLoading ? 'Saving...' : account.password_is_permanent ? 'Update Password' : 'Set Permanent Password'}
            </button>
          </form>
        </section>

        {/* Padam Akaun */}
        <section style={{ ...sectionStyle, borderColor: '#FECACA' }}>
          <h2 style={{ ...sectionHeadingStyle, color: '#DC2626' }}>Padam Akaun</h2>
          <p style={{ fontSize: 14, color: 'var(--ink-soft)', margin: '0 0 16px', lineHeight: 1.6 }}>
            Dokumen dan perbualan anda akan dipadam sepenuhnya. Rekod transaksi pembayaran dikekalkan tanpa nama untuk tujuan audit kewangan.
          </p>
          <button
            onClick={() => setDeleteStep(1)}
            style={{ padding: '10px 20px', background: '#EF4444', color: '#fff', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, cursor: 'pointer' }}
          >
            Padam Akaun Saya
          </button>
        </section>
      </div>

      {/* Delete Confirm Modal */}
      {deleteStep === 1 && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999, padding: 24 }}>
          <div style={{ background: 'var(--card)', borderRadius: 'var(--radius-lg)', padding: 32, maxWidth: 440, width: '100%' }}>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 12px', color: '#DC2626' }}>Sahkan Pemadaman Akaun</h2>
            <p style={{ fontSize: 14, color: 'var(--ink-soft)', margin: '0 0 8px', lineHeight: 1.6 }}>
              Dokumen dan perbualan anda akan dipadam sepenuhnya. Rekod transaksi pembayaran dikekalkan tanpa nama untuk tujuan audit kewangan.
            </p>
            <p style={{ fontSize: 14, margin: '0 0 16px' }}>
              Taip <strong>PADAM</strong> untuk sahkan:
            </p>
            <input
              value={deleteInput}
              onChange={e => setDeleteInput(e.target.value)}
              placeholder="PADAM"
              style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-mono)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)', marginBottom: 16, boxSizing: 'border-box' }}
            />
            {deleteError && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 12px' }}>{deleteError}</p>}
            <div style={{ display: 'flex', gap: 12 }}>
              <button
                onClick={() => { setDeleteStep(0); setDeleteInput(''); setDeleteError('') }}
                style={{ flex: 1, padding: '10px 0', background: 'transparent', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', cursor: 'pointer' }}
              >
                Batal
              </button>
              <button
                onClick={handleDeleteAccount}
                disabled={deleteInput !== 'PADAM' || deleteLoading}
                style={{ flex: 1, padding: '10px 0', background: deleteInput === 'PADAM' ? '#EF4444' : 'var(--line)', color: deleteInput === 'PADAM' ? '#fff' : 'var(--ink-soft)', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, cursor: deleteInput === 'PADAM' ? 'pointer' : 'not-allowed' }}
              >
                {deleteLoading ? 'Processing...' : 'Delete Account'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const sectionStyle = {
  background: 'var(--card)', border: '1px solid var(--line)',
  borderRadius: 'var(--radius-md)', padding: '24px', marginBottom: 20,
}
const sectionHeadingStyle = {
  fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 16,
  margin: '0 0 16px',
}
const rowStyle = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  paddingBottom: 12, marginBottom: 12, borderBottom: '1px solid var(--line)',
}
const labelStyle = { fontSize: 14, color: 'var(--ink-soft)' }
const valueStyle = { fontSize: 14, fontWeight: 500 }
