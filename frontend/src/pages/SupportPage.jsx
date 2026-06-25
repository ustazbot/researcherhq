import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'

const CATEGORIES = [
  { value: 'bug', label: 'Pepijat / Masalah Teknikal' },
  { value: 'billing', label: 'Pembayaran & Langganan' },
  { value: 'kredit', label: 'Research Credits' },
  { value: 'lain-lain', label: 'Lain-lain' },
]

export function SupportPage() {
  const nav = useNavigate()
  const [category, setCategory] = useState('bug')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [reportId, setReportId] = useState(null)
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    if (!description.trim()) return
    setLoading(true)
    setError('')
    try {
      const { data } = await api.post('/support/report', { category, description })
      setReportId(data.report_id)
    } catch (err) {
      setError(err.response?.data?.detail || 'Gagal hantar laporan. Cuba lagi.')
    }
    setLoading(false)
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', padding: '40px 24px' }}>
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <button onClick={() => nav('/')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)', fontSize: 14, marginBottom: 24, padding: 0 }}>
          ← Back to Dashboard
        </button>
        <h1 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, margin: '0 0 8px' }}>
          Report an Issue
        </h1>
        <p style={{ color: 'var(--ink-soft)', fontSize: 14, margin: '0 0 32px' }}>
          Fill in the form below. We'll get back to you as soon as possible.
        </p>

        {reportId ? (
          <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 'var(--radius-md)', padding: '24px' }}>
            <p style={{ fontWeight: 600, color: '#15803D', margin: '0 0 8px' }}>Laporan diterima. Terima kasih.</p>
            <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: '0 0 4px' }}>No. Rujukan: <code>{reportId.slice(0, 8).toUpperCase()}</code></p>
            <button onClick={() => nav('/')} style={{ marginTop: 16, padding: '8px 16px', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontFamily: 'var(--font-heading)', fontWeight: 700 }}>
              Back to Dashboard
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: 'var(--radius-md)', padding: 32 }}>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 500, marginBottom: 8 }}>
                Category
              </label>
              <select
                value={category}
                onChange={e => setCategory(e.target.value)}
                style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)' }}
              >
                {CATEGORIES.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 500, marginBottom: 8 }}>
                Description
              </label>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Describe your issue clearly..."
                required
                rows={5}
                style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-body)', fontSize: 14, background: 'var(--bg)', color: 'var(--ink)', resize: 'vertical', boxSizing: 'border-box' }}
              />
            </div>
            {error && <p style={{ color: '#EF4444', fontSize: 13, margin: '0 0 16px' }}>{error}</p>}
            <button type="submit" disabled={loading || !description.trim()} style={{ width: '100%', padding: '12px 0', background: 'var(--ink)', color: 'var(--bg)', border: 'none', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: 15, cursor: 'pointer' }}>
              {loading ? 'Sending...' : 'Send Report'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
